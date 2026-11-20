"""The coach: what it reads, how it's called, the checks on its report, backfill, failures."""

import json
from datetime import datetime
from typing import Any

import pytest

from app.coaching.analysis import analyse
from app.coaching.coach import (
    COACH_MAX_TOKENS,
    COACH_TEMPERATURE,
    MAX_ITEMS,
    Checked,
    CoachOutcome,
    check_report,
    run_coach,
)
from app.coaching.report import CoachReport, MissedPoint
from app.llm import InvalidOutput, ModelTimeout, Role
from app.llm.fake import FakeLLM, Scripted
from app.prompts import PROMPT_VERSION, render
from app.simulation import Language, Session
from tests.coaching_factory import (
    ASK_PAYMENTS,
    ASK_PLANS,
    ASK_SHARIA,
    NOT_IN_KEY,
    coach_reply,
    interview,
    missed_item,
    real_interview,
)
from tests.content_factory import ALPHA, BETA
from tests.interview_factory import OPENING, T0

ALL_FOUND = (ASK_PAYMENTS, ASK_SHARIA, ASK_PLANS)


def clock() -> datetime:
    return T0


def check(session: Session, reply: dict[str, Any], language: Language = "en") -> Checked:
    report = CoachReport.model_validate(reply)
    return check_report(report, session=session, analysis=analyse(session), language=language)


def checked(
    session: Session, reply: dict[str, Any], language: Language = "en"
) -> tuple[CoachReport, tuple[str, ...]]:
    result = check(session, reply, language)
    return result.report, result.backfilled


async def coach(
    session: Session, *replies: Scripted, language: Language = "en"
) -> tuple[CoachOutcome, FakeLLM]:
    fake = FakeLLM({Role.COACH: replies})
    outcome = await run_coach(fake, session, analyse(session), language, clock=clock)
    return outcome, fake


async def test_a_valid_report_passes_through_unchanged() -> None:
    session = interview(*ALL_FOUND, recommend=[BETA])
    reply = coach_reply(
        went_well=[{"point": "You asked how her customers pay.", "evidence_turns": [1]}],
        missed=[missed_item("Explain why the overdraft wouldn't fit.", product_id=ALPHA)],
        how_to_improve=[
            {"tip": "Ask about values early.", "example": "Does Islamic banking matter?"}
        ],
    )

    outcome, fake = await coach(session, reply)

    assert outcome.report == CoachReport.model_validate(reply)
    assert (outcome.degraded, outcome.backfilled, outcome.error_code) == (False, (), None)
    assert (outcome.json_retried, outcome.generated_at) == (False, T0)
    (call,) = fake.calls_for(Role.COACH)
    assert (call.method, call.schema, call.model) == ("chat_json", CoachReport, "coach-model")
    assert (
        (call.max_tokens, call.temperature) == (COACH_MAX_TOKENS, COACH_TEMPERATURE) == (1500, 0.3)
    )
    assert call.prompt_version == PROMPT_VERSION["coach"]


async def test_the_coach_reads_the_whole_profile_the_numbered_transcript_and_the_analysis() -> None:
    session = interview(ASK_PAYMENTS, recommend=[ALPHA])

    outcome, fake = await coach(session, coach_reply(), language="ar")

    system, user = fake.calls_for(Role.COACH)[0].messages
    assert system.content == render("coach")
    data = json.loads(user.content)
    assert data["output_language"] == "ar"
    assert data["transcript"] == [
        f"[t0] Client: {OPENING}",
        "[t1] Student: How do your customers pay?",
        "[t2] Client: I see.",
    ]
    assert data["student_turns"] == [1]
    # The interview is over: the coach sees every fact, including those still locked.
    contents = [fact["content"] for fact in data["client"]["hidden_facts"]]
    assert contents == [fact.content for fact in session.client.hidden_facts]
    assert data["client"]["needs"][0]["description_ar"] == "تمويل الفجوة."
    assert data["coach_notes"]["key_questions"] == list(session.client.coach_notes.key_questions)
    assert data["wrapup"]["recommendations"] == [{"product_id": ALPHA, "reason": "It fits."}]
    assert [need["status"] for need in data["analysis"]["needs"]] == ["partial", "missed"]
    assert data["analysis"]["products"][0]["verdict"] == "unsuitable"
    assert data["example_questions_for_missed_facts"] == {
        "sharia": ["Tell me about sharia?"],
        "expansion": ["Tell me about expansion?"],
    }
    assert {product["id"] for product in data["catalogue"]} == {ALPHA, BETA}
    assert outcome.degraded is False


def test_turns_that_are_not_the_students_are_dropped_and_unknown_ids_become_null() -> None:
    session = interview(*ALL_FOUND, recommend=[BETA])
    reply = coach_reply(
        went_well=[{"point": "Good opening.", "evidence_turns": [0, 3, 1, 2, 99, 3]}],
        missed=[
            missed_item(need_id=" FUND-gap ", product_id="Alpha-Loan", evidence_turns=[4, 5]),
            missed_item("Another point.", need_id="no-such-need", product_id=NOT_IN_KEY),
        ],
    )

    report, backfilled = checked(session, reply)

    assert report.went_well[0].evidence_turns == [1, 3]
    first, second = report.missed
    assert (first.need_id, first.product_id, first.evidence_turns) == ("fund-gap", ALPHA, [5])
    assert (second.need_id, second.product_id) == (None, None)
    assert backfilled == ()


def test_each_list_keeps_four_items_and_items_without_text_are_dropped() -> None:
    session = interview(*ALL_FOUND, recommend=[BETA])
    reply = coach_reply(
        went_well=[{"point": f"Point {i}.", "evidence_turns": [1]} for i in range(6)],
        missed=[missed_item("   "), *(missed_item(f"Missed {i}.") for i in range(5))],
        how_to_improve=[{"tip": "", "example": None}, {"tip": "Ask more.", "example": "  "}],
    )

    report, _ = checked(session, reply)

    assert [item.point for item in report.went_well] == [f"Point {i}." for i in range(MAX_ITEMS)]
    assert [item.point for item in report.missed] == [f"Missed {i}." for i in range(MAX_ITEMS)]
    assert [(item.tip, item.example) for item in report.how_to_improve] == [("Ask more.", None)]


def test_a_missed_critical_need_without_an_entry_is_backfilled_first() -> None:
    # `fund-gap` is partly uncovered: its critical fact `sharia` is still locked.
    session = interview(ASK_PAYMENTS, recommend=[BETA])
    reply = coach_reply(missed=[missed_item(f"Missed {i}.") for i in range(MAX_ITEMS)])

    report, backfilled = checked(session, reply)

    assert backfilled == ("fund-gap",)
    assert report.missed[0] == MissedPoint(
        point="Fund the gap.",
        need_id="fund-gap",
        product_id=None,
        evidence_turns=[],
        better_question="Tell me about sharia?",
    )
    # Never more than four: the model's last entry makes room.
    assert [item.point for item in report.missed[1:]] == ["Missed 0.", "Missed 1.", "Missed 2."]


def test_a_backfilled_entry_uses_the_arabic_description_in_arabic() -> None:
    session = interview(ASK_PAYMENTS, recommend=[BETA])

    report, backfilled = checked(session, coach_reply(), language="ar")

    assert backfilled == ("fund-gap",)
    assert report.missed[0].point == "تمويل الفجوة."


def test_a_missed_critical_need_the_model_covered_is_not_backfilled() -> None:
    session = interview(ASK_PAYMENTS, recommend=[BETA])

    report, backfilled = checked(session, coach_reply(missed=[missed_item(need_id="Fund-Gap")]))

    assert backfilled == ()
    assert [item.need_id for item in report.missed] == ["fund-gap"]


async def test_invalid_output_degrades_the_feedback() -> None:
    session = interview(ASK_PAYMENTS, recommend=[BETA])

    outcome, _ = await coach(session, InvalidOutput("unusable JSON after one retry"))

    assert (outcome.report, outcome.degraded) == (None, True)
    assert (outcome.error_code, outcome.json_retried, outcome.backfilled) == (
        "INVALID_OUTPUT",
        True,
        (),
    )


async def test_a_reply_that_isnt_a_report_degrades_the_feedback() -> None:
    session = interview(ASK_PAYMENTS, recommend=[BETA])

    outcome, _ = await coach(session, '{"went_well": "lots"}')

    assert (outcome.report, outcome.degraded, outcome.error_code) == (None, True, "INVALID_OUTPUT")


async def test_any_model_error_degrades_the_feedback() -> None:
    session = interview(ASK_PAYMENTS, recommend=[BETA])

    outcome, _ = await coach(session, ModelTimeout("the model did not answer in time"))

    assert (outcome.report, outcome.degraded) == (None, True)
    assert (outcome.error_code, outcome.json_retried) == ("MODEL_TIMEOUT", False)


def test_praise_that_cites_no_student_turn_is_dropped() -> None:
    # qwen's weak run in the M5 report: praise for something the student never did.
    session = interview(*ALL_FOUND, recommend=[BETA])
    reply = coach_reply(
        went_well=[
            {
                "point": "You built rapport quickly by acknowledging her busy schedule and "
                "showing genuine interest in her business growth.",
                "evidence_turns": [],
            },
            {"point": "You asked how her customers pay.", "evidence_turns": [1]},
        ]
    )

    result = check(session, reply)

    assert [item.point for item in result.report.went_well] == ["You asked how her customers pay."]
    assert [(drop.section, drop.reason) for drop in result.dropped] == [
        ("went_well", "no_student_turn")
    ]
    assert result.dropped[0].text.startswith("You built rapport quickly")


def test_praise_for_the_pitch_of_an_unsuitable_product_is_dropped() -> None:
    # The Arabic UI run in the M5 report: praise citing turn 7, the overdraft pitch.
    session = real_interview(
        "noura-al-kuwari",
        ("شكرًا على حضورك. هل يمكنك أن تحدثيني قليلًا عن شركتك؟", [], []),
        ("كم يستغرق عملاؤك عادةً حتى يسددوا فواتيرك؟", ["late-payments"], []),
        ("هل لديك عقود كبيرة أو خطط للتوسع في الفترة القادمة؟", ["big-contract"], []),
        ("أقترح عليك السحب على المكشوف للأعمال.", ["sharia-only"], ["sharia-only"]),
        recommend=["business-overdraft", "murabaha-working-capital"],
        pitched={"business-overdraft": [7]},
    )
    reply = coach_reply(
        went_well=[
            {
                "point": "أنت طرحت أسئلة ممتازة حول تدفق السيولة والعقود الكبيرة، مما ساعدك على "
                "كشف احتياجاتها المالية الأساسية.",
                "evidence_turns": [3, 5],
            },
            {
                "point": "لقد استمعت جيدًا إلى رد العميل وأخذت بعين الاعتبار طلبها بالتأكد من "
                "توافق المنتج مع الشريعة قبل الإجابة.",
                "evidence_turns": [7],
            },
        ]
    )

    result = check(session, reply, language="ar")

    assert [item.evidence_turns for item in result.report.went_well] == [[3, 5]]
    assert [(drop.section, drop.reason) for drop in result.dropped] == [
        ("went_well", "cites_unsuitable_pitch")
    ]


def test_praise_for_a_turn_that_the_missed_section_cites_is_dropped() -> None:
    session = interview(*ALL_FOUND, recommend=[BETA])
    reply = coach_reply(
        went_well=[
            {"point": "A good question about her plans.", "evidence_turns": [5]},
            {"point": "You asked how her customers pay.", "evidence_turns": [1]},
        ],
        missed=[missed_item("The plans question came too late.", evidence_turns=[5])],
    )

    result = check(session, reply)

    assert [item.point for item in result.report.went_well] == ["You asked how her customers pay."]
    assert [drop.reason for drop in result.dropped] == ["cites_missed_turn"]


def test_dropped_praise_leaves_room_for_grounded_praise() -> None:
    session = interview(*ALL_FOUND, recommend=[BETA])
    ungrounded = [{"point": f"Ungrounded {i}.", "evidence_turns": []} for i in range(2)]
    grounded = [{"point": f"Point {i}.", "evidence_turns": [1]} for i in range(MAX_ITEMS)]

    result = check(session, coach_reply(went_well=[*ungrounded, *grounded]))

    assert [item.point for item in result.report.went_well] == [g["point"] for g in grounded]
    assert len(result.dropped) == 2


async def test_the_outcome_carries_the_drops() -> None:
    session = interview(*ALL_FOUND, recommend=[BETA])
    reply = coach_reply(went_well=[{"point": "Lovely rapport.", "evidence_turns": []}])

    outcome, _ = await coach(session, reply)

    assert outcome.report is not None and outcome.report.went_well == []
    assert [drop.reason for drop in outcome.dropped] == ["no_student_turn"]


NOURA_WEAK = (
    ("Thanks for coming in. Could you tell me a bit about yourself?", [], []),
    ("I'd suggest our Business Overdraft.", ["sharia-only"], ["sharia-only"]),
)


def noura_weak() -> Session:
    return real_interview(
        "noura-al-kuwari",
        *NOURA_WEAK,
        recommend=["business-overdraft"],
        pitched={"business-overdraft": [3]},
    )


def test_questions_and_examples_that_name_a_product_are_cleared_and_their_items_kept() -> None:
    # Phrasing from qwen's weak report in the M5 appendix.
    murabaha = (
        "We offer a Sharia-compliant Murabaha facility where we buy your stock and sell it to "
        "you with a fixed profit. Would that interest-free structure work for you?"
    )
    collect = (
        "To speed up payments from your corporate clients, we also have a Business Collect "
        "Account with automatic invoice reminders. Would that be useful?"
    )
    reply = coach_reply(
        missed=[
            missed_item("You didn't offer a Sharia-compliant option.", better_question=murabaha)
        ],
        how_to_improve=[{"tip": "Suggest tools for slow payers.", "example": collect}],
    )

    result = check(noura_weak(), reply)

    (missed,) = [item for item in result.report.missed if item.point.startswith("You didn't")]
    assert missed.better_question is None
    (tip,) = result.report.how_to_improve
    assert (tip.tip, tip.example) == ("Suggest tools for slow payers.", None)
    assert [(item.section, item.field, item.reason) for item in result.cleared] == [
        ("missed", "better_question", "names_a_product"),
        ("how_to_improve", "example", "names_a_product"),
    ]


def test_arabic_names_aliases_and_ids_are_caught_too() -> None:
    questions = [
        "هل يناسبك تمويل رأس المال العامل بالمرابحة؟",  # an alias inside a word
        "ما رأيك في خصم الفواتير؟",  # the full Arabic name of the invoice advance
        "Would murabaha-working-capital help?",  # an id
    ]
    reply = coach_reply(
        missed=[missed_item(f"Point {i}.", better_question=q) for i, q in enumerate(questions)]
    )

    result = check(noura_weak(), reply, language="ar")

    model_items = [item for item in result.report.missed if item.point.startswith("Point")]
    assert [item.better_question for item in model_items] == [None, None, None]
    assert len(result.cleared) == 3


def test_discovery_questions_without_a_product_name_are_kept() -> None:
    questions = [
        "كم يستغرق عملاؤك عادةً حتى يسددوا فواتيرك؟",
        "Do you have an overdraft today?",  # an everyday word, not the product's name
        "How do you cover salaries while you wait to be paid?",
    ]
    reply = coach_reply(
        missed=[missed_item(f"Point {i}.", better_question=q) for i, q in enumerate(questions)]
    )

    result = check(noura_weak(), reply)

    model_items = [item for item in result.report.missed if item.point.startswith("Point")]
    assert [item.better_question for item in model_items] == questions
    assert result.cleared == ()


@pytest.mark.parametrize(
    ("example", "shown"),
    [
        # From the M5 appendix: an example nested inside quotes.
        (
            "Before suggesting credit, ask: 'Do you prefer Sharia-compliant products or "
            "conventional ones?'",
            "Before suggesting credit, ask: Do you prefer Sharia-compliant products or "
            "conventional ones?",
        ),
        ('"How quickly do your customers pay you?"', "How quickly do your customers pay you?"),
        ("“What matters to you in a bank?”", "What matters to you in a bank?"),
        ("«هل تفضلين المنتجات المتوافقة مع الشريعة؟»", "هل تفضلين المنتجات المتوافقة مع الشريعة؟"),
        (
            "What's the hardest part? Don't your suppliers wait?",
            "What's the hardest part? Don't your suppliers wait?",
        ),
        ("‘How do you pay staff?’", "How do you pay staff?"),
    ],
)
def test_examples_and_questions_lose_their_own_quotation_marks(example: str, shown: str) -> None:
    session = interview(*ALL_FOUND, recommend=[BETA])
    reply = coach_reply(
        missed=[missed_item(better_question=example)],
        how_to_improve=[{"tip": "Ask early.", "example": example}],
    )

    report = check(session, reply).report

    assert report.missed[0].better_question == shown
    assert report.how_to_improve[0].example == shown


def test_latin_words_in_an_arabic_report_are_counted_not_rejected() -> None:
    session = interview(*ALL_FOUND, recommend=[BETA])
    reply = coach_reply(
        went_well=[{"point": "سألتَ عن طريقة السداد مبكرًا.", "evidence_turns": [1]}],
        how_to_improve=[
            {"tip": "السؤال عن التفضيلات قبل اقتراح أي منتج في قطاع SME.", "example": None}
        ],
        summary="ملخصك دقيق.",
    )

    arabic = check(session, reply, language="ar")
    english = check(session, reply, language="en")

    assert arabic.mixed_script == 1
    assert arabic.report.how_to_improve[0].tip.endswith("قطاع SME.")  # kept as written
    assert english.mixed_script == 0


async def test_the_coach_reads_the_clients_grammatical_gender() -> None:
    session = interview(ASK_PAYMENTS, recommend=[ALPHA])

    _, fake = await coach(session, coach_reply(), language="ar")

    data = json.loads(fake.calls_for(Role.COACH)[0].messages[1].content)
    assert data["client"]["persona"]["gender"] == "female"


async def test_the_coach_reads_when_the_client_had_already_ruled_a_product_out() -> None:
    session = real_interview(
        "noura-al-kuwari",
        ("What do you need from the bank?", ["sharia-only"], []),
        ("I'd suggest our Business Overdraft.", [], []),
        recommend=["business-overdraft"],
        pitched={"business-overdraft": [3]},
    )

    _, fake = await coach(session, coach_reply())

    data = json.loads(fake.calls_for(Role.COACH)[0].messages[1].content)
    (verdict,) = data["analysis"]["products"]
    assert (verdict["ruled_out_at"], verdict["pitched_at"]) == (2, 3)
