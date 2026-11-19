"""Health endpoint: is the app up, can it reach the model endpoint, are the models there?"""

import time
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.dto import EndpointOut, HealthOut, HealthStatus, ModelsOut, ModelStatusOut
from app.config import Settings, get_settings
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
class _Cached:
    value: HealthOut
    expires_at: float


def _app_version() -> str:
    try:
        return version("bank-discovery-simulator")
    except PackageNotFoundError:
        return "0.0.0"


@router.get("/health", response_model=HealthOut)
async def health(
    request: Request,
    llm: Annotated[LLMClient, Depends(llm_dep)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthOut:
    """Report the app version, the model endpoint and each role's model.

    Always HTTP 200: the body says whether the models can be used. Cached for 30 seconds.
    """
    cached: _Cached | None = getattr(request.app.state, "health_cache", None)
    if cached is not None and _now() < cached.expires_at:
        return cached.value
    value = await _check(llm, settings)
    request.app.state.health_cache = _Cached(value, _now() + CACHE_TTL_S)
    return value


async def _check(llm: LLMClient, settings: Settings) -> HealthOut:
    host = endpoint_host(settings.LLM_BASE_URL)
    names = {role: resolve_model(role, None, settings=settings) for role in Role}
    try:
        listed = await llm.list_models()
    except LLMError as exc:
        reachable, hint = _down_hint(exc, host)
        return _report("down", host, reachable, names, set(), hint)
    available = {_canonical(name) for name in listed}
    present = {name for name in names.values() if _canonical(name) in available}
    missing = [name for name in dict.fromkeys(names.values()) if name not in present]
    hint = " ".join(f"Model {name} not found. Run: ollama pull {name}" for name in missing)
    return _report("degraded" if missing else "ok", host, True, names, present, hint or None)


def _down_hint(exc: LLMError, host: str) -> tuple[bool, str]:
    """Return (endpoint reachable, hint) for a failed model listing."""
    if isinstance(exc, ModelTimeout) or (
        isinstance(exc, ModelUnavailable) and exc.reason == "unreachable"
    ):
        return False, f"Cannot reach the model endpoint at {host}. Is Ollama running?"
    if isinstance(exc, ModelUnavailable) and exc.reason == "auth":
        return True, f"The model endpoint at {host} rejected the API key. Check LLM_API_KEY."
    return True, f"The model endpoint at {host} answered with an error. Check LLM_BASE_URL."


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
) -> HealthOut:
    def model(role: Role) -> ModelStatusOut:
        return ModelStatusOut(name=names[role], available=names[role] in present)

    return HealthOut(
        status=status,
        version=_app_version(),
        endpoint=EndpointOut(reachable=reachable, host=host),
        models=ModelsOut(gate=model(Role.GATE), client=model(Role.CLIENT), coach=model(Role.COACH)),
        hint=hint,
    )
