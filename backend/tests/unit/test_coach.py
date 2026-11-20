"""The coach: what it reads, how it's called, the checks on its report, backfill, failures."""

import json
from datetime import datetime
from typing import Any

from app.coaching.analysis import analyse
from app.coaching.coach import (
    COACH_MAX_TOKENS,
    COACH_TEMPERATURE,
    MAX_ITEMS,
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
)
from tests.content_factory import ALPHA, BETA
from tests.interview_factory import OPENING, T0

ALL_FOUND = (ASK_PAYMENTS, ASK_SHARIA, ASK_PLANS)


def clock() -> datetime:
    return T0


def checked(
    session: Session, reply: dict[str, Any], language: Language = "en"
) -> tuple[CoachReport, tuple[str, ...]]:
    report = CoachReport.model_validate(reply)
    return check_report(report, session=session, analysis=analyse(session), language=language)


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
        went_well=[{"point": f"Point {i}.", "evidence_turns": []} for i in range(6)],
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
