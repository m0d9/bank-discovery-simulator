"""FeedbackService: the one code path for feedback and the export, for the API, scripts/ and
evals/."""

import hashlib
import json
import time
from collections import Counter
from dataclasses import dataclass

from app.coaching.analysis import analyse
from app.coaching.cache import CoachCache
from app.coaching.coach import CoachOutcome, run_coach
from app.coaching.export import export_filename, export_markdown
from app.coaching.feedback import Feedback, latest_feedback
from app.config import Settings
from app.llm import LLMClient
from app.prompts import PROMPT_VERSION
from app.simulation import InvalidState, Language, Session, SessionStatus, SessionStore
from app.telemetry.events import EventLogger


@dataclass(frozen=True)
class ExportFile:
    """A download: its file name and its Markdown text."""

    filename: str
    text: str


def cache_key(session: Session, language: Language) -> str:
    """sha256 of everything the coach's report depends on: the client's content, the
    transcript, the wrap-up, the coach model, the coach prompt's version and the language.
    Raises ValueError without a wrap-up."""
    if session.wrapup is None:
        raise ValueError("the session has no wrap-up yet")
    payload = {
        "client": session.client.model_dump(mode="json"),
        "transcript": [[turn.n, turn.role, turn.text] for turn in session.turns],
        "wrapup": session.wrapup.model_dump(mode="json"),
        "coach_model": session.models.coach,
        "prompt_version": PROMPT_VERSION["coach"],
        "language": language,
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class FeedbackService:
    """Feedback on wrapped-up interviews, and the Markdown export.

    Build one per request (the API) or once per process (scripts, evals). The sessions live in
    the `SessionStore` and the coach's reports in the `CoachCache`, so the service itself holds
    no state.
    """

    def __init__(
        self,
        *,
        store: SessionStore,
        llm: LLMClient,
        settings: Settings,
        events: EventLogger,
        cache: CoachCache,
    ) -> None:
        self._store = store
        self._llm = llm
        self._settings = settings
        self._events = events
        self._cache = cache

    async def feedback(self, session_id: str, language: Language) -> tuple[Session, Feedback]:
        """Analyse the session and ask the coach for its report in `language`; the status
        becomes `feedback_ready`.

        Allowed once the interview is wrapped up, and again afterwards: the same transcript in
        the same language reuses the cached report without calling the model, and a call still
        running is shared. A coach failure doesn't raise: the feedback is degraded, and it isn't
        cached, so asking again retries. Raises `SessionNotFound` or `InvalidState`.
        """
        session = self._store.get(session_id)
        self._store.touch(session_id)
        if session.status is SessionStatus.INTERVIEWING or session.wrapup is None:
            raise InvalidState("feedback is available once the interview is wrapped up")
        analysis = analyse(session)
        started = time.perf_counter()
        outcome, reused = await self._cache.get_or_run(
            cache_key(session, language),
            lambda: run_coach(self._llm, session, analysis, language, clock=self._store.now),
        )
        feedback = Feedback(
            language=language,
            analysis=analysis,
            report=outcome.report,
            degraded=outcome.degraded,
            generated_at=outcome.generated_at,
            backfilled=outcome.backfilled,
        )
        session.feedback = feedback
        session.status = SessionStatus.FEEDBACK_READY
        await self._emit(session, feedback, outcome, reused, _since(started))
        return session, feedback

    def export(self, session_id: str) -> ExportFile:
        """The session as a Markdown file. Raises `SessionNotFound`."""
        session = self._store.get(session_id)
        self._store.touch(session_id)
        return ExportFile(
            filename=export_filename(session),
            text=export_markdown(session, latest_feedback(session)),
        )

    async def _emit(
        self,
        session: Session,
        feedback: Feedback,
        outcome: CoachOutcome,
        reused: bool,
        latency_ms: int,
    ) -> None:
        stats = feedback.analysis.stats
        if not reused:
            # Only when the coach really ran: a cache hit reuses the same checked report.
            for drop in outcome.dropped:
                fields: dict[str, object] = {
                    "session_id": session.id,
                    "client_id": session.client_id,
                    "section": drop.section,
                    "reason": drop.reason,
                }
                if self._settings.LOG_TRANSCRIPTS:
                    fields["text"] = drop.text
                await self._events.emit("coach_item_dropped", **fields)
        await self._events.emit(
            "feedback_generated",
            session_id=session.id,
            client_id=session.client_id,
            language=feedback.language,
            degraded=feedback.degraded,
            error=outcome.error_code,
            backfilled=len(outcome.backfilled),
            dropped=dict(Counter(drop.section for drop in outcome.dropped)),
            cleared=dict(Counter(f"{item.section}.{item.field}" for item in outcome.cleared)),
            mixed_script=outcome.mixed_script,
            cached=reused,
            json_retried=outcome.json_retried,
            latency_ms=latency_ms,
            needs_uncovered=stats.needs_uncovered,
            needs_after_pitch=stats.needs_after_pitch,
            needs_total=stats.needs_total,
            critical_found=stats.critical_found,
            critical_total=stats.critical_total,
            recommended=[
                {"product_id": verdict.product_id, "verdict": verdict.verdict}
                for verdict in feedback.analysis.products
            ],
            model=session.models.coach,
            prompt_version=PROMPT_VERSION["coach"],
        )


def _since(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
