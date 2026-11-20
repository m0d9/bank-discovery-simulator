"""The Markdown export: its sections before and after feedback, Arabic, escaping, file name."""

from app.coaching.analysis import analyse
from app.coaching.export import LABELS, export_filename, export_markdown
from app.coaching.feedback import Feedback
from app.coaching.report import CoachReport
from app.content import Client
from app.simulation import Session
from tests.coaching_factory import (
    ASK_PAYMENTS,
    ASK_PLANS,
    NOT_IN_KEY,
    Step,
    coach_reply,
    coaching_client_data,
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


def test_a_need_completed_by_a_pitch_is_labelled_after_a_pitch() -> None:
    pitch: Step = ("I'd suggest our Alpha Loan.", ["sharia"], ["sharia"])
    session, feedback = with_feedback(ASK_PAYMENTS, pitch, recommend=[ALPHA])

    text = export_markdown(session, feedback)

    assert "| Fund the gap. | After a pitch | Turn 3 | I'd suggest our Alpha Loan. |" in text


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

    assert text.startswith('<div dir="rtl">\n\n# \u2068مقابلة مع عميل الاختبار\u2069\n')
    assert text.endswith("\n</div>\n")
    # Free text is isolated (FSI…PDI), so English keeps its direction, full stop included.
    assert "**الرسالة 1 · \u2068أنت\u2069:** \u2068How do your customers pay?\u2069" in text
    assert "\u2068SECRET-CASH-GAP: the content of cash-gap.\u2069" in text
    assert (
        "| \u2068تمويل الفجوة.\u2069 | \u2068مكتشَف جزئيًا\u2069 | \u2068–\u2069 | \u2068–\u2069 |"
        in text
    )


def test_an_english_export_has_no_isolates() -> None:
    session, feedback = with_feedback(ASK_PAYMENTS, recommend=[ALPHA])

    text = export_markdown(session, feedback)

    assert "\u2068" not in text and "\u2069" not in text


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


def test_the_export_shows_each_distinct_reason_once() -> None:
    data = coaching_client_data()
    data["needs"][1]["suitable_products"] = [BETA]
    data["needs"][1]["unsuitable_products"] = [{"id": ALPHA, "reason": "Interest-based."}]
    session = interview(ASK_PAYMENTS, recommend=[ALPHA])
    session.client = Client.model_validate(data)
    feedback = Feedback(
        language="en", analysis=analyse(session), report=None, degraded=True, generated_at=T0
    )

    text = export_markdown(session, feedback)

    # Alpha Loan is unsuitable for both needs, for the same reason: it's given once.
    assert "- **Alpha Loan: Not suitable.** Interest-based.\n" in text


def test_a_product_the_client_had_already_ruled_out_says_so() -> None:
    session, feedback = with_feedback(ASK_PAYMENTS, recommend=[ALPHA])
    (verdict,) = feedback.analysis.products
    ruled = verdict.model_copy(update={"ruled_out_at": 2})
    analysis = feedback.analysis.model_copy(update={"products": (ruled,)})

    text = export_markdown(session, feedback.model_copy(update={"analysis": analysis}))

    assert (
        "- **Alpha Loan: Not suitable.** Interest-based. The client had already said something "
        "that rules this out (Turn 2)." in text
    )


def test_the_ruled_out_line_is_in_arabic_in_an_arabic_export() -> None:
    session, english = with_feedback(ASK_PAYMENTS, recommend=[ALPHA])
    (verdict,) = english.analysis.products
    ruled = verdict.model_copy(update={"ruled_out_at": 2})
    analysis = english.analysis.model_copy(update={"products": (ruled,)})
    arabic = english.model_copy(update={"language": "ar", "analysis": analysis})

    text = export_markdown(session, arabic)

    assert "كانت المقابلة قد كشفت ما يستبعد هذا المنتج (الرسالة 2)." in text


def test_a_note_under_the_coachs_sections_says_that_a_model_wrote_them() -> None:
    session, feedback = with_feedback(ASK_PAYMENTS, recommend=[ALPHA])

    text = export_markdown(session, feedback)

    note = (
        "*The AI coach wrote these notes and can make mistakes. The discovery map and the "
        "verdicts above come from the answer key.*"
    )
    assert note in text
    assert text.index(f"## {LABELS['en']['discovery_map']}") < text.index(note)
    assert text.index(note) < text.index(f"### {LABELS['en']['about_summary']}")


def test_the_coach_note_is_in_arabic_and_only_with_a_report() -> None:
    session, english = with_feedback(ASK_PAYMENTS, recommend=[ALPHA])

    arabic = export_markdown(session, english.model_copy(update={"language": "ar"}))
    unavailable = export_markdown(session, english.model_copy(update={"report": None}))

    assert (
        "*كتب المدرّب الافتراضي هذه الملاحظات وقد يخطئ. أما خريطة الاكتشاف وتقييم توصياتك أعلاه "
        "فمبنيان على الإجابة النموذجية.*" in arabic
    )
    assert LABELS["en"]["coach_note"] not in unavailable
