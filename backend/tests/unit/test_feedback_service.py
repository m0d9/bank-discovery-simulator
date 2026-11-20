"""FeedbackService: the state rule, the cache, a shared running call, degraded feedback, the
event and the export."""

import asyncio
import json
from typing import Any

import pytest

from app.coaching import CoachCache, CoachReport, FeedbackService, latest_feedback
from app.coaching.coach import CoachOutcome
from app.coaching.service import cache_key
from app.config import Settings
from app.llm import ModelTimeout, Role
from app.llm.fake import FakeLLM
from app.simulation import InvalidState, Session, SessionNotFound, SessionStatus, SessionStore
from app.telemetry.events import EventLogger
from tests.coaching_factory import ASK_PAYMENTS, coach_reply, interview, missed_item
from tests.content_factory import ALPHA, BETA
from tests.interview_factory import T0

REPORT = coach_reply(
    went_well=[{"point": "You asked how her customers pay.", "evidence_turns": [1]}],
    missed=[missed_item("You never asked about her values.", need_id="fund-gap")],
)


@pytest.fixture
def store() -> SessionStore:
    return SessionStore(ttl_minutes=120, max_sessions=10, clock=lambda: T0)


@pytest.fixture
def fake() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def service(settings: Settings, store: SessionStore, fake: FakeLLM) -> FeedbackService:
    return FeedbackService(
        store=store,
        llm=fake,
        events=EventLogger(settings.DATA_DIR / "events.jsonl"),
        cache=CoachCache(),
    )


def wrapped(store: SessionStore, *, status: SessionStatus = SessionStatus.WRAPPED_UP) -> Session:
    session = interview(ASK_PAYMENTS, recommend=[ALPHA])
    session.status = status
    store.create(session)
    return session


def events(settings: Settings) -> list[dict[str, Any]]:
    path = settings.DATA_DIR / "events.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return [json.loads(line) for line in lines]


async def test_feedback_needs_a_wrapped_up_interview(
    service: FeedbackService, store: SessionStore, fake: FakeLLM
) -> None:
    session = wrapped(store, status=SessionStatus.INTERVIEWING)

    with pytest.raises(InvalidState):
        await service.feedback(session.id, "en")
    with pytest.raises(SessionNotFound):
        await service.feedback("no-such-session", "en")
    assert fake.calls == []
    assert session.status is SessionStatus.INTERVIEWING


async def test_feedback_analyses_asks_the_coach_and_marks_the_session_ready(
    service: FeedbackService, store: SessionStore, fake: FakeLLM
) -> None:
    session = wrapped(store)
    fake.script(Role.COACH, REPORT)

    returned, feedback = await service.feedback(session.id, "en")

    assert returned is session
    assert session.status is SessionStatus.FEEDBACK_READY
    assert latest_feedback(session) == feedback
    assert (feedback.language, feedback.degraded, feedback.generated_at) == ("en", False, T0)
    assert feedback.report == CoachReport.model_validate(REPORT)
    assert feedback.analysis.products[0].verdict == "unsuitable"
    assert feedback.backfilled == ()


async def test_asking_again_reuses_the_report_without_calling_the_model(
    service: FeedbackService, store: SessionStore, fake: FakeLLM
) -> None:
    session = wrapped(store)
    fake.script(Role.COACH, REPORT)

    _, first = await service.feedback(session.id, "en")
    _, second = await service.feedback(session.id, "en")

    assert second == first
    assert len(fake.calls_for(Role.COACH)) == 1


async def test_each_language_gets_its_own_report(
    service: FeedbackService, store: SessionStore, fake: FakeLLM
) -> None:
    session = wrapped(store)
    arabic = coach_reply(summary="ملخصك يذكر الفجوة النقدية.")
    fake.script(Role.COACH, REPORT, arabic)

    await service.feedback(session.id, "en")
    _, in_arabic = await service.feedback(session.id, "ar")
    _, english_again = await service.feedback(session.id, "en")

    assert in_arabic.report is not None and in_arabic.report.summary_feedback.startswith("ملخصك")
    assert english_again.language == "en"
    assert latest_feedback(session) == english_again
    assert len(fake.calls_for(Role.COACH)) == 2


async def test_requests_while_the_coach_is_writing_share_its_call(
    service: FeedbackService, store: SessionStore, fake: FakeLLM
) -> None:
    session = wrapped(store)
    fake.script(Role.COACH, REPORT)

    (_, first), (_, second) = await asyncio.gather(
        service.feedback(session.id, "en"), service.feedback(session.id, "en")
    )

    assert first == second
    assert len(fake.calls_for(Role.COACH)) == 1


async def test_degraded_feedback_isnt_cached_so_asking_again_retries_the_coach(
    service: FeedbackService, store: SessionStore, fake: FakeLLM
) -> None:
    session = wrapped(store)
    fake.script(Role.COACH, ModelTimeout("the model did not answer in time"), REPORT)

    _, degraded = await service.feedback(session.id, "en")
    status_after_failure = session.status
    _, retried = await service.feedback(session.id, "en")

    assert (degraded.degraded, degraded.report) == (True, None)
    assert degraded.analysis == retried.analysis
    assert status_after_failure is SessionStatus.FEEDBACK_READY
    assert (retried.degraded, retried.report) == (False, CoachReport.model_validate(REPORT))
    assert len(fake.calls_for(Role.COACH)) == 2


async def test_the_event_has_ids_counts_and_verdicts_but_no_text(
    service: FeedbackService, store: SessionStore, fake: FakeLLM, settings: Settings
) -> None:
    session = wrapped(store)
    fake.script(Role.COACH, coach_reply())  # no entry for `fund-gap`: one is backfilled

    await service.feedback(session.id, "en")
    await service.feedback(session.id, "en")

    first, second = (event for event in events(settings) if event["event"] == "feedback_generated")
    assert {key: first[key] for key in first if key not in {"ts", "latency_ms"}} == {
        "event": "feedback_generated",
        "session_id": session.id,
        "client_id": session.client_id,
        "language": "en",
        "degraded": False,
        "error": None,
        "backfilled": 1,
        "cached": False,
        "json_retried": False,
        "needs_uncovered": 0,
        "needs_total": 2,
        "critical_found": 1,
        "critical_total": 2,
        "recommended": [{"product_id": ALPHA, "verdict": "unsuitable"}],
        "model": "coach-model",
        "prompt_version": first["prompt_version"],
    }
    assert isinstance(first["latency_ms"], int)
    assert second["cached"] is True
    text = json.dumps(events(settings), ensure_ascii=False)
    for private in ("How do your customers pay?", "Your summary names", "bridge late payments"):
        assert private not in text


async def test_the_export_adds_the_feedback_once_it_exists(
    service: FeedbackService, store: SessionStore, fake: FakeLLM
) -> None:
    session = wrapped(store)
    fake.script(Role.COACH, REPORT)

    before = service.export(session.id)
    await service.feedback(session.id, "en")
    after = service.export(session.id)

    assert before.filename == after.filename == "interview-test-client-20261120.md"
    assert "Coach feedback" not in before.text
    assert "## Coach feedback" in after.text
    assert "You never asked about her values." in after.text
    with pytest.raises(SessionNotFound):
        service.export("no-such-session")


def test_the_cache_key_depends_on_the_language_the_model_and_the_transcript() -> None:
    session = interview(ASK_PAYMENTS, recommend=[ALPHA])
    other_model = session.model_copy(
        update={"models": session.models.model_copy(update={"coach": "other"})}
    )
    other_wrapup = interview(ASK_PAYMENTS, recommend=[BETA])
    longer = interview(ASK_PAYMENTS, ASK_PAYMENTS, recommend=[ALPHA])

    key = cache_key(session, "en")

    assert key == cache_key(interview(ASK_PAYMENTS, recommend=[ALPHA]), "en")
    assert len({key, cache_key(session, "ar"), cache_key(other_model, "en")}) == 3
    assert key not in {cache_key(other_wrapup, "en"), cache_key(longer, "en")}


async def test_the_cache_keeps_its_most_recently_used_entries() -> None:
    cache = CoachCache(max_entries=2)
    runs: list[str] = []

    def run(name: str) -> Any:
        async def coach() -> CoachOutcome:
            runs.append(name)
            return CoachOutcome(
                report=CoachReport.model_validate(coach_reply()),
                degraded=False,
                backfilled=(),
                latency_ms=1,
                json_retried=False,
                error_code=None,
                generated_at=T0,
            )

        return coach

    for name in ("a", "b", "a", "c", "a", "b"):
        await cache.get_or_run(name, run(name))

    # "b" was the least recently used when "c" arrived, so it ran twice.
    assert runs == ["a", "b", "c", "b"]
    assert len(cache) == 2
