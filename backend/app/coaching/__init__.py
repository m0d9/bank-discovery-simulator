"""Coaching: the deterministic analysis, the AI coach, the feedback and the export.

Import from here. `FeedbackService` is the single code path for feedback, used by the API,
`scripts/` and `evals/`. The coach's reports are kept in one `CoachCache` per process.
"""

from app.coaching.analysis import (
    Analysis,
    DiscoveredBy,
    FactResult,
    FactUnlock,
    MissedOpportunity,
    NeedResult,
    NeedStatus,
    ProductVerdict,
    Stats,
    Verdict,
    VerdictReason,
    Via,
    analyse,
)
from app.coaching.cache import CoachCache
from app.coaching.coach import CoachOutcome, run_coach
from app.coaching.feedback import Feedback, latest_feedback
from app.coaching.report import CoachReport, Improvement, MissedPoint, WentWell
from app.coaching.service import ExportFile, FeedbackService

__all__ = [
    "Analysis",
    "CoachCache",
    "CoachOutcome",
    "CoachReport",
    "DiscoveredBy",
    "ExportFile",
    "FactResult",
    "FactUnlock",
    "Feedback",
    "FeedbackService",
    "Improvement",
    "MissedOpportunity",
    "MissedPoint",
    "NeedResult",
    "NeedStatus",
    "ProductVerdict",
    "Stats",
    "Verdict",
    "VerdictReason",
    "Via",
    "WentWell",
    "analyse",
    "latest_feedback",
    "run_coach",
]
