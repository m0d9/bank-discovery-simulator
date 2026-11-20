"""Interviews: sessions, the disclosure gate and the AI client.

Import from here. `InterviewService` is the single code path for the API, `scripts/` and
`evals/`; the sessions it works on live in a `SessionStore`.
"""

from app.simulation.client_agent import FALLBACK_LINES, breaks_character, normalise
from app.simulation.errors import (
    InterviewError,
    InvalidInput,
    InvalidState,
    SessionBusy,
    SessionNotFound,
    TurnLimitReached,
)
from app.simulation.models import (
    Language,
    Recommendation,
    Session,
    SessionModels,
    SessionStatus,
    Turn,
    WrapUp,
)
from app.simulation.service import InterviewService, TurnResult
from app.simulation.store import SessionStore

__all__ = [
    "FALLBACK_LINES",
    "InterviewError",
    "InterviewService",
    "InvalidInput",
    "InvalidState",
    "Language",
    "Recommendation",
    "Session",
    "SessionBusy",
    "SessionModels",
    "SessionNotFound",
    "SessionStatus",
    "SessionStore",
    "Turn",
    "TurnLimitReached",
    "TurnResult",
    "WrapUp",
    "breaks_character",
    "normalise",
]
