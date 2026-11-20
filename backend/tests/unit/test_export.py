"""The Markdown export: its sections before and after feedback, Arabic, escaping, file name."""

from app.coaching.analysis import analyse
from app.coaching.export import LABELS, export_filename, export_markdown
from app.coaching.feedback import Feedback
from app.coaching.report import CoachReport
from app.simulation import Session
from tests.coaching_factory import (
    ASK_PAYMENTS,
    ASK_PLANS,
    NOT_IN_KEY,
    Step,
    coach_reply,
    interview,
    missed_item,
)
from tests.content_factory import ALPHA, BETA
from tests.interview_factory import T0

REPORT = coach_reply(
    went_well=[{"point": "You asked how her customers pay.", "evidence_turns": [1, 3]}],
    missed=[missed_item("Ask about values.", need_id="fund-gap", evidence_turns=[3])],
    how_to_improve=[{"tip": "Ask before you pitch.", "example": "What matters to you?"}],
    summary="Your summary names the cash gap.",
)


def with_feedback(
    *steps: Step, recommend: list[str], report: dict[str, object] | None = REPORT
) -> tuple[Session, Feedback]:
    session = interview(*steps, recommend=recommend)
    feedback = Feedback(
        language="en",
        analysis=analyse(session),
        report=CoachReport.model_validate(report) if report is not None else None,
        degraded=report is None,
        generated_at=T0,
    )
    return session, feedback


def test_before_feedback_the_export_has_the_transcript_and_the_wrap_up_only() -> None:
    session = interview(ASK_PAYMENTS, recommend=[ALPHA])

    text = export_markdown(session, None)

    assert text.startswith("# Interview with Test Client\n")
    assert "- **Date:** 2026-11-20" in text
    assert (
        "AI client `client-model` · Disclosure gate `gate-model` · AI coach `coach-model`" in text
    )
    assert "**Turn 0 · Test Client:** Hello, I have a few minutes." in text
    assert "**Turn 1 · You:** How do your customers pay?" in text
    assert "> The client needs to bridge late payments and grow." in text
    assert "- **Alpha Loan:** It fits." in text
    for later in ("Discovery map", "Coach feedback", "Behind the scenes", "SECRET-"):
        assert later not in text
    assert text.rstrip().endswith("Fictional bank for tests.")


def test_with_feedback_it_adds_the_map_the_verdicts_the_coach_and_the_profile() -> None:
    session, feedback = with_feedback(ASK_PAYMENTS, ASK_PLANS, recommend=[ALPHA, NOT_IN_KEY])

    text = export_markdown(session, feedback)

    sections = [line for line in text.splitlines() if line.startswith("#")]
    assert sections == [
        "# Interview with Test Client",
        "## Transcript",
        "## Your summary and recommendations",
        "### Your summary",
        "### Your recommendations",
        "## Discovery map",
        "## Your recommendations against the answer key",
        "### Suitable products you didn't recommend",
        "## Coach feedback",
        "### What went well",
        "### What was missed",
        "### How to improve",
        "### About your summary",
        "## Behind the scenes: the full client profile",
        "### Persona",
        "### What the client shares freely",
        "### Hidden facts",
        "### Needs (the answer key)",
    ]
    assert "| Fund the gap. | Partly uncovered | – | – |" in text
    assert "| Grow the business. | Uncovered | Turn 3 | What are your plans? |" in text
    assert "- **Alpha Loan: Not suitable.** Interest-based." in text
    assert f"- **{NOT_IN_KEY}: Not in the answer key.**" in text
    assert "- **Beta Deposit.** Meets: Fund the gap.; Grow the business." in text
    assert "- You asked how her customers pay. (Turns: 1, 3)" in text
    assert "A question you could have asked: “What are your plans?”" in text
    assert "For example: “What matters to you?”" in text
    assert "SECRET-CASH-GAP: the content of cash-gap.  \n  Critical · Found at turn 1" in text
    assert "SECRET-SHARIA: the content of sharia.  \n  Critical · Not found" in text
    assert "**Fund the gap.** (Partly uncovered)" in text
    assert "Unsuitable products: Alpha Loan (Interest-based.)" in text


def test_a_fact_brought_out_by_a_pitch_says_so() -> None:
    pitch: Step = ("I'd suggest our Alpha Loan.", ["sharia"], ["sharia"])
    session, feedback = with_feedback(pitch, recommend=[ALPHA])

    assert "in reaction to a product you proposed" in export_markdown(session, feedback)


def test_degraded_feedback_says_the_coach_was_unavailable() -> None:
    session, feedback = with_feedback(ASK_PAYMENTS, recommend=[ALPHA], report=None)

    text = export_markdown(session, feedback)

    assert LABELS["en"]["coach_unavailable"] in text
    assert "### What went well" not in text
    assert "## Discovery map" in text


def test_an_arabic_export_uses_arabic_labels_and_reads_right_to_left() -> None:
    session, english = with_feedback(ASK_PAYMENTS, recommend=[ALPHA])
    arabic = english.model_copy(update={"language": "ar"})

    text = export_markdown(session, arabic)

    assert text.startswith('<div dir="rtl">\n\n# مقابلة مع عميل الاختبار\n')
    assert text.endswith("\n</div>\n")
    assert "**الرسالة 1 · أنت:** How do your customers pay?" in text
    assert "| تمويل الفجوة. | اكتُشف جزئيًا | – | – |" in text


def test_text_from_students_and_models_cannot_add_markup() -> None:
    risky: Step = ("# Heading?\n- item | <b>bold</b> *star* [link](x)\n1. one", [], [])
    session = interview(risky, recommend=[BETA])

    text = export_markdown(session, None)

    assert (
        "**Turn 1 · You:** \\# Heading?  \n\\- item \\| \\<b\\>bold\\</b\\> \\*star\\* "
        "\\[link\\](x)  \n1\\. one"
    ) in text


def test_the_file_name_has_the_client_and_the_date_the_interview_started() -> None:
    assert export_filename(interview(recommend=[ALPHA])) == "interview-test-client-20261120.md"
