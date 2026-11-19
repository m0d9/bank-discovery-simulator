"""Model roles, and how each role picks its model and timeout."""

from enum import StrEnum

from app.config import Settings, get_settings


class Role(StrEnum):
    """Who is calling the model. Each role can use its own model and timeout."""

    GATE = "gate"
    CLIENT = "client"
    COACH = "coach"


def resolve_model(
    role: Role, override: str | None = None, *, settings: Settings | None = None
) -> str:
    """Return the model for `role`: the override, else the role's own setting, else LLM_MODEL."""
    if override:
        return override
    s = settings or get_settings()
    per_role = {
        Role.GATE: s.LLM_MODEL_GATE,
        Role.CLIENT: s.LLM_MODEL_CLIENT,
        Role.COACH: s.LLM_MODEL_COACH,
    }[role]
    return per_role or s.LLM_MODEL


def role_timeout(role: Role, settings: Settings) -> float:
    """Return the per-request timeout for `role`, in seconds."""
    return {
        Role.GATE: settings.LLM_TIMEOUT_GATE_S,
        Role.CLIENT: settings.LLM_TIMEOUT_CLIENT_S,
        Role.COACH: settings.LLM_TIMEOUT_COACH_S,
    }[role]
