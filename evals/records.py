"""What a run records: each turn, each session, the coach's outcome and the judge's verdicts.

The traces (gitignored) keep everything. The committed summary leaves out the client's
replies, the gate's notes and the session snapshots (`SUMMARY_EXCLUDE`).
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.simulation import Language
from evals.scenarios import ScriptName

Section = Literal["went_well", "missed", "summary_feedback"]
Phase = Literal["setup", "interview", "coach", "judge"]


class LanguageRetryRecord(BaseModel):
    """The client answered in the wrong language and was asked again."""

    reason: str
    retried: bool
    fixed: bool
    first_text: str = ""
    """The reply in the wrong language (traces only: the summary leaves it out)."""


class TurnRecord(BaseModel):
    """One scripted student line and what happened behind it."""

    line: int
    """The line's index in the script, from 0."""
    kind: str
    student: str
    n: int | None = None
    """The student turn's number in the app (1, 3, 5…), or None when the turn failed."""
    client: str | None = None
    eligible: list[str] = Field(default_factory=list)
    unlocked: list[str] = Field(default_factory=list)
    by_pitch: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    gate_failed: bool = False
    gate_rejected: list[str] = Field(default_factory=list)
    gate_quotes: dict[str, str] = Field(default_factory=dict)
    gate_note: str = ""
    role_break: bool = False
    """The fallback line was used: the reply broke character twice."""
    regenerated: bool = False
    """The first reply broke character (the pattern check) and was regenerated."""
    pattern_break: bool = False
    """The reply the student saw matches the character-break pattern."""
    language_retry: LanguageRetryRecord | None = None
    latency_ms: dict[str, int] = Field(default_factory=dict)
    error: str | None = None


class CoachRecord(BaseModel):
    """The feedback on one session, and what the code guards did to the coach's report."""

    language: Language
    model: str
    prompt_version: str
    degraded: bool
    error: str | None = None
    json_retried: bool = False
    backfilled: list[str] = Field(default_factory=list)
    dropped: dict[str, int] = Field(default_factory=dict)
    """Dropped items by section, from `feedback_generated`."""
    dropped_reasons: dict[str, int] = Field(default_factory=dict)
    """Dropped items by reason, from the `coach_item_dropped` events."""
    cleared: dict[str, int] = Field(default_factory=dict)
    mixed_script: int = 0
    needs_after_pitch: int = 0
    latency_ms: int = 0
    missed_critical: list[str] = Field(default_factory=list)
    """Needs with a critical fact still locked: the ones the coach must address."""
    report: dict[str, Any] | None = None
    analysis: dict[str, Any] | None = None


class ReplyJudgement(BaseModel):
    """The judge on one adversarial reply. `judged` is False when its call failed."""

    n: int
    """The client reply's turn number."""
    judged: bool
    breaks_character: bool | None = None
    revealed: list[str] = Field(default_factory=list)
    evidence: dict[str, str] = Field(default_factory=dict)
    unknown_ids: list[str] = Field(default_factory=list)
    """Fact ids the judge named that weren't locked at that turn: ignored."""
    note: str = ""


class ItemJudgement(BaseModel):
    """The judge on one item of a coach report. `supported` is None when unjudged."""

    section: Section
    index: int
    """The item's position in its section of the report."""
    text: str
    evidence_turns: list[int] = Field(default_factory=list)
    supported: bool | None = None
    category: str | None = None
    reason: str = ""


class ArabicJudgement(BaseModel):
    """The judge on one Arabic report: how it addresses the student and the client."""

    student_address: str
    student_examples: list[str] = Field(default_factory=list)
    client_agreement: str
    client_examples: list[str] = Field(default_factory=list)
    note: str = ""


class JudgeRecord(BaseModel):
    """Every verdict on one session."""

    replies: list[ReplyJudgement] = Field(default_factory=list)
    items: list[ItemJudgement] = Field(default_factory=list)
    arabic: ArabicJudgement | None = None
    errors: list[str] = Field(default_factory=list)


class SessionRecord(BaseModel):
    """One scripted interview: its turns, the feedback, the verdicts, and (in the traces) the
    session itself, which the replay restores."""

    key: str
    client_id: str
    script: ScriptName
    language: Language
    session_id: str | None = None
    pitched: str | None = None
    expected: dict[str, list[int]] = Field(default_factory=dict)
    allowed: dict[str, list[int]] = Field(default_factory=dict)
    turns: list[TurnRecord] = Field(default_factory=list)
    error: str | None = None
    coach: CoachRecord | None = None
    judge: JudgeRecord = Field(default_factory=JudgeRecord)
    snapshot: dict[str, Any] | None = None


class EventRecord(BaseModel):
    """One telemetry event, tagged with the session it belongs to and the run's phase."""

    event: str
    key: str | None
    phase: Phase
    fields: dict[str, Any]


class RunInfo(BaseModel):
    """Everything about a run except its sessions and metrics."""

    format: Literal[1] = 1
    config: str
    stamp: str
    note: str = ""
    replay_of: str | None = None
    models: dict[str, str]
    judge: dict[str, Any]
    settings: dict[str, Any]
    git: dict[str, Any]
    prompt_versions: dict[str, str]
    judge_prompt_versions: dict[str, str]
    clients: list[str]
    scripts: list[str]
    complete: bool
    started_at: str
    duration_s: float = 0.0


class RunSummary(RunInfo):
    """The committed results of one run."""

    metrics: dict[str, Any]
    sessions: list[SessionRecord]


# Left out of the committed summary: they're in the traces.
SUMMARY_EXCLUDE: dict[str, Any] = {
    "sessions": {
        "__all__": {
            "snapshot": True,
            "turns": {
                "__all__": {"client": True, "gate_note": True, "language_retry": {"first_text"}}
            },
            "coach": {"analysis"},
        }
    }
}
