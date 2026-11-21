"""Health endpoint: is the app up, can it reach the model endpoint, are the models there, and
are the content files valid?"""

import time
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request

from app.api.dto import (
    ContentStatusDTO,
    EndpointDTO,
    HealthDTO,
    HealthHintCode,
    HealthStatus,
    ModelsDTO,
    ModelStatusDTO,
)
from app.config import Settings, get_settings
from app.content import ContentStore, get_content_store
from app.llm import (
    LLMClient,
    LLMError,
    ModelTimeout,
    ModelUnavailable,
    Role,
    endpoint_host,
    llm_dep,
    resolve_model,
)

router = APIRouter(tags=["health"])

CACHE_TTL_S = 30.0
_now = time.monotonic  # module-level so tests can move the clock


@dataclass(frozen=True)
class _ModelReport:
    """Everything in the health response except the content status."""

    status: HealthStatus
    version: str
    endpoint: EndpointDTO
    models: ModelsDTO
    hint: str | None
    hint_code: HealthHintCode | None


@dataclass(frozen=True)
class _Cached:
    value: _ModelReport
    expires_at: float


def _app_version() -> str:
    try:
        return version("bank-discovery-simulator")
    except PackageNotFoundError:
        return "0.0.0"


@router.get("/health", response_model=HealthDTO)
async def health(
    request: Request,
    llm: Annotated[LLMClient, Depends(llm_dep)],
    settings: Annotated[Settings, Depends(get_settings)],
    content: Annotated[ContentStore, Depends(get_content_store)],
) -> HealthDTO:
    """Report the app version, the model endpoint, each role's model and the content status.

    Always HTTP 200: the body says whether the models can be used. A good model check is
    cached for 30 seconds; a problem is checked again on every call, so Retry sees a
    restarted endpoint at once, and a failed model call clears the cache. The content status
    is checked on every call, so a broken file shows up as soon as the store notices it.
    """
    await content.refresh()
    report = await _model_report(request, llm, settings)
    status = content.status
    return HealthDTO(
        status=report.status,
        version=report.version,
        endpoint=report.endpoint,
        models=report.models,
        hint=report.hint,
        hint_code=report.hint_code,
        content=ContentStatusDTO(ok=status.ok, errors=list(status.errors)),
    )


async def _model_report(request: Request, llm: LLMClient, settings: Settings) -> _ModelReport:
    cached: _Cached | None = getattr(request.app.state, "health_cache", None)
    if cached is not None and _now() < cached.expires_at:
        return cached.value
    value = await _check(llm, settings)
    if value.status == "ok":
        request.app.state.health_cache = _Cached(value, _now() + CACHE_TTL_S)
    return value


def forget_cached_health(app: FastAPI) -> None:
    """Drop the cached model check, so the next `/api/health` checks the endpoint again."""
    app.state.health_cache = None


async def _check(llm: LLMClient, settings: Settings) -> _ModelReport:
    host = endpoint_host(settings.LLM_BASE_URL)
    names = {role: resolve_model(role, None, settings=settings) for role in Role}
    try:
        listed = await llm.list_models()
    except LLMError as exc:
        reachable, hint, code = _down_hint(exc, host)
        return _report("down", host, reachable, names, set(), hint, code)
    available = {_canonical(name) for name in listed}
    present = {name for name in names.values() if _canonical(name) in available}
    missing = [name for name in dict.fromkeys(names.values()) if name not in present]
    if not missing:
        return _report("ok", host, True, names, present, None, None)
    hint = " ".join(f"Model {name} not found. Run: ollama pull {name}" for name in missing)
    return _report("degraded", host, True, names, present, hint, "MODEL_MISSING")


def _down_hint(exc: LLMError, host: str) -> tuple[bool, str, HealthHintCode]:
    """Return (endpoint reachable, hint, hint code) for a failed model listing."""
    if isinstance(exc, ModelTimeout) or (
        isinstance(exc, ModelUnavailable) and exc.reason == "unreachable"
    ):
        hint = f"Cannot reach the model endpoint at {host}. Is Ollama running?"
        return False, hint, "ENDPOINT_UNREACHABLE"
    if isinstance(exc, ModelUnavailable) and exc.reason == "auth":
        hint = f"The model endpoint at {host} rejected the API key. Check LLM_API_KEY."
        return True, hint, "ENDPOINT_AUTH"
    hint = f"The model endpoint at {host} answered with an error. Check LLM_BASE_URL."
    return True, hint, "ENDPOINT_ERROR"


def _canonical(name: str) -> str:
    # Ollama lists untagged models as `name:latest`.
    return name if ":" in name else f"{name}:latest"


def _report(
    status: HealthStatus,
    host: str,
    reachable: bool,
    names: dict[Role, str],
    present: set[str],
    hint: str | None,
    hint_code: HealthHintCode | None,
) -> _ModelReport:
    def model(role: Role) -> ModelStatusDTO:
        return ModelStatusDTO(name=names[role], available=names[role] in present)

    return _ModelReport(
        status=status,
        version=_app_version(),
        endpoint=EndpointDTO(reachable=reachable, host=host),
        models=ModelsDTO(gate=model(Role.GATE), client=model(Role.CLIENT), coach=model(Role.COACH)),
        hint=hint,
        hint_code=hint_code,
    )
