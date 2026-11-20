"""The feedback on a session, as the session keeps it."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.coaching.analysis import Analysis
from app.coaching.report import CoachReport
from app.simulation import Language, Session


class Feedback(BaseModel):
    """The feedback in one language: the analysis, and the coach's report unless the coach
    failed (`degraded`)."""

    model_config = ConfigDict(frozen=True)

    language: Language
    analysis: Analysis
    report: CoachReport | None
    degraded: bool
    generated_at: datetime
    backfilled: tuple[str, ...] = ()
    """Missed critical needs that code added to the report because the model left them out."""


def latest_feedback(session: Session) -> Feedback | None:
    """The feedback generated last for the session, if any."""
    return session.feedback if isinstance(session.feedback, Feedback) else None
