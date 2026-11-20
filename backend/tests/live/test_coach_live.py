"""The milestone's live acceptance runs: a weak and a strong interview with Noura, then the
coach, against the real models in `.env`. Run with `make test-live`.

The models sample their replies, so a failure here is a finding to report, not a test to loosen.
"""

import pytest

from app.coaching import CoachCache, Feedback, FeedbackService
from app.config import get_settings
from app.content import load_registry
from app.llm.client import OpenAICompatClient
from app.simulation import InterviewService, Recommendation, Session, SessionStore, WrapUp
from app.telemetry.events import event_logger_for

pytestmark = pytest.mark.live

NOURA = "noura-al-kuwari"
# M7's weak script: generic questions, then a pitch of an unsuitable product.
WEAK = (
    "Thanks for coming in. Could you tell me a bit about yourself?",
    "How is business going at the moment?",
    "What brings you in today?",
    "Is there anything else I should know?",
    "I'd suggest our Business Overdraft: a flexible credit limit on your business account for "
    "when cash is short.",
    "So would that work for you?",
)
# M7's strong script: each fact's first example question, in dependency order, then a pitch.
STRONG = (
    "Thanks for coming in. Could you tell me a bit about your situation?",
    "How quickly do your customers usually pay you?",
    "Do you have any preferences about the kind of banking products you use?",
    "Are there any big contracts or growth plans coming up?",
    "I'd suggest our Murabaha Working Capital: the bank buys the goods you need and sells them "
    "to you at an agreed profit, paid back in instalments.",
)


async def interview_then_feedback(
    messages: tuple[str, ...], wrapup: WrapUp
) -> tuple[Session, Feedback]:
    # Fresh clients per test: each test runs on its own event loop.
    settings = get_settings()
    store = SessionStore.from_settings(settings)
    llm = OpenAICompatClient(settings)
    events = event_logger_for(settings.DATA_DIR)
    interview = InterviewService(
        store=store,
        llm=llm,
        settings=settings,
        events=events,
        content=load_registry(settings.CONTENT_DIR),
    )
    feedback = FeedbackService(store=store, llm=llm, events=events, cache=CoachCache())
    session = await interview.create_session(NOURA, "en")
    for message in messages:
        await interview.student_message(session.id, message)
    await interview.wrap_up(session.id, wrapup)
    return await feedback.feedback(session.id, "en")


async def test_weak_interview_feedback_flags_the_cash_gap_and_the_overdraft() -> None:
    wrapup = WrapUp(
        needs_summary="The client wants better banking services.",
        recommendations=[
            Recommendation(product_id="business-overdraft", reason="Flexible cash when short.")
        ],
    )

    _, feedback = await interview_then_feedback(WEAK, wrapup)

    assert not feedback.degraded and feedback.report is not None
    (overdraft,) = feedback.analysis.products
    assert overdraft.verdict == "unsuitable" and overdraft.reasons
    cash_gap = [item for item in feedback.report.missed if item.need_id == "bridge-cash-gap"]
    assert cash_gap, feedback.report.missed
    assert all(item.better_question for item in cash_gap), cash_gap


async def test_strong_interview_feedback_cites_the_students_turns() -> None:
    wrapup = WrapUp(
        needs_summary=(
            "Government-linked clients pay her 90 to 120 days late, so she has paid salaries "
            "from her savings. She only uses Sharia-compliant products, and a school catering "
            "contract would need about QAR 300,000 of stock up front."
        ),
        recommendations=[
            Recommendation(
                product_id="murabaha-working-capital", reason="Sharia-compliant stock financing."
            )
        ],
    )

    session, feedback = await interview_then_feedback(STRONG, wrapup)

    assert not feedback.degraded and feedback.report is not None
    student_turns = {turn.n for turn in session.turns if turn.role == "student"}
    went_well = feedback.report.went_well
    assert went_well and any(item.evidence_turns for item in went_well), went_well
    assert all(set(item.evidence_turns) <= student_turns for item in went_well)
    assert [need.status for need in feedback.analysis.needs] == ["uncovered", "uncovered"]
