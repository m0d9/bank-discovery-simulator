"""The `llm_call` telemetry payload and its cost estimate."""

from pydantic import BaseModel, ConfigDict

from app.config import Settings
from app.llm.roles import Role
from app.llm.types import JsonMode

_PER_MILLION = 1_000_000


class LLMCallEvent(BaseModel):
    """Fields of one `llm_call` event: measurements only, never message text."""

    model_config = ConfigDict(frozen=True)

    role: Role
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int
    attempts: int
    outcome: str
    json_mode: JsonMode
    est_cost_usd: float | None
    prompt_version: str | None


def estimate_cost_usd(
    prompt_tokens: int | None, completion_tokens: int | None, settings: Settings
) -> float | None:
    """Estimate a call's cost from LLM_PRICE_*_PER_MTOK; None when neither price is set."""
    price_in = settings.LLM_PRICE_INPUT_PER_MTOK
    price_out = settings.LLM_PRICE_OUTPUT_PER_MTOK
    if price_in is None and price_out is None:
        return None
    cost = (prompt_tokens or 0) * (price_in or 0) + (completion_tokens or 0) * (price_out or 0)
    return round(cost / _PER_MILLION, 8)
