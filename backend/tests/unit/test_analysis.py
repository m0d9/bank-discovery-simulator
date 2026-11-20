"""The deterministic analysis: needs, facts, product verdicts, missed opportunities, counts."""

import pytest

from app.coaching.analysis import (
    FactUnlock,
    MissedOpportunity,
    VerdictReason,
    Via,
    analyse,
    missed_critical_needs,
    product_verdict,
)
from app.content import Client, LocalizedText
from tests.coaching_factory import NOT_IN_KEY, coaching_client_data, interview, real_interview
from tests.content_factory import ALPHA, BETA
from tests.interview_factory import make_session


def test_every_need_found_is_uncovered_via_the_turn_that_completed_it() -> None:
    session = interview(
        ("How do your customers pay?", ["cash-gap"], []),
        ("Is Islamic banking important to you?", ["sharia"], []),
        ("What are your plans?", ["expansion"], []),
        recommend=[BETA],
    )

    analysis = analyse(session)

    fund_gap, grow = analysis.needs
    assert (fund_gap.need_id, fund_gap.status) == ("fund-gap", "uncovered")
    assert fund_gap.facts == (
        FactUnlock(fact_id="cash-gap", unlocked_at_turn=1),
        FactUnlock(fact_id="sharia", unlocked_at_turn=3),
    )
    assert fund_gap.via == Via(turn=3, question="Is Islamic banking important to you?")
    assert (grow.status, grow.via) == ("uncovered", Via(turn=5, question="What are your plans?"))
    assert analysis.stats.model_dump() == {
        "student_turns": 3,
        "needs_uncovered": 2,
        "needs_after_pitch": 0,
        "needs_total": 2,
        "critical_found": 2,
        "critical_total": 2,
        "first_unlock_turn": 1,
    }


def test_a_need_is_partial_when_some_facts_are_found_and_missed_when_none_are() -> None:
    session = interview(("How do your customers pay?", ["cash-gap"], []), recommend=[BETA])

    fund_gap, grow = analyse(session).needs

    assert (fund_gap.status, fund_gap.via) == ("partial", None)
    assert fund_gap.facts[1] == FactUnlock(fact_id="sharia", unlocked_at_turn=None)
    assert (grow.status, grow.via) == ("missed", None)


def test_nothing_found_means_every_need_is_missed_and_no_first_unlock() -> None:
    session = interview(("Tell me about yourself.", [], []), recommend=[BETA])

    analysis = analyse(session)

    assert [need.status for need in analysis.needs] == ["missed", "missed"]
    assert analysis.stats.needs_uncovered == 0
    assert (analysis.stats.critical_found, analysis.stats.critical_total) == (0, 2)
    assert analysis.stats.first_unlock_turn is None


def test_each_fact_says_when_and_how_it_came_out() -> None:
    session = interview(
        ("How do your customers pay?", ["cash-gap"], []),
        ("I'd suggest our Alpha Loan.", ["sharia"], ["sharia"]),
        recommend=[ALPHA],
    )

    facts = {fact.fact_id: fact for fact in analyse(session).facts}

    assert (facts["cash-gap"].unlocked_at_turn, facts["cash-gap"].discovered_by) == (1, "question")
    assert (facts["sharia"].unlocked_at_turn, facts["sharia"].discovered_by) == (
        3,
        "product_pitch",
    )
    assert (facts["expansion"].unlocked_at_turn, facts["expansion"].discovered_by) == (None, None)
    assert facts["expansion"].importance == "important"


def test_verdict_precedence_unsuitable_then_suitable_then_not_in_key() -> None:
    session = interview(("How do your customers pay?", ["cash-gap"], []), recommend=[ALPHA])
    client = session.client

    # ALPHA is suitable for `grow` but unsuitable for `fund-gap`: unsuitable wins.
    unsuitable = product_verdict(client, ALPHA)
    suitable = product_verdict(client, BETA)
    unknown = product_verdict(client, NOT_IN_KEY)

    assert (unsuitable.verdict, unsuitable.needs) == ("unsuitable", ())
    assert unsuitable.reasons == (
        VerdictReason(need_id="fund-gap", reason=LocalizedText(en="Interest-based.")),
    )
    assert (suitable.verdict, suitable.needs, suitable.reasons) == (
        "suitable",
        ("fund-gap", "grow"),
        (),
    )
    assert (unknown.verdict, unknown.needs, unknown.reasons) == ("not_in_key", (), ())
    assert [verdict.product_id for verdict in analyse(session).products] == [ALPHA]


def test_without_a_catalogue_fit_every_product_is_unsuitable_because_of_the_referral() -> None:
    note = {"en": "Refer him to trade finance.", "ar": "إحالته إلى قسم تمويل التجارة."}
    data = coaching_client_data(no_catalogue_fit=True, referral_note=note)
    for need in data["needs"]:
        need["suitable_products"], need["unsuitable_products"] = [], []
    session = interview(("How do your customers pay?", ["cash-gap"], []), recommend=[BETA])
    session.client = Client.model_validate(data)

    analysis = analyse(session)

    (verdict,) = analysis.products
    assert verdict.verdict == "unsuitable"
    assert verdict.reasons == (VerdictReason(need_id=None, reason=LocalizedText(**note)),)
    assert analysis.missed_opportunities == ()


def test_missed_opportunities_are_suitable_products_for_needs_the_student_found() -> None:
    session = interview(
        ("How do your customers pay?", ["cash-gap"], []),
        ("What are your plans?", ["expansion"], []),
        recommend=[NOT_IN_KEY],
    )

    analysis = analyse(session)

    # `fund-gap` is partial and `grow` uncovered. ALPHA would suit `grow`, but it's
    # unsuitable for `fund-gap`, so recommending it wouldn't have been right either.
    assert analysis.missed_opportunities == (
        MissedOpportunity(product_id=BETA, needs=("fund-gap", "grow")),
    )


def test_missed_needs_and_recommended_products_are_not_missed_opportunities() -> None:
    nothing_found = interview(("Tell me about yourself.", [], []), recommend=[NOT_IN_KEY])
    recommended = interview(("How do your customers pay?", ["cash-gap"], []), recommend=[BETA])

    assert analyse(nothing_found).missed_opportunities == ()
    assert analyse(recommended).missed_opportunities == ()


def test_missed_critical_needs_include_partly_uncovered_ones() -> None:
    partial = interview(("How do your customers pay?", ["cash-gap"], []), recommend=[BETA])
    complete = interview(
        ("How do your customers pay?", ["cash-gap"], []),
        ("Is Islamic banking important to you?", ["sharia"], []),
        recommend=[BETA],
    )

    # `fund-gap` still has `sharia` (critical) locked. `grow` is missed, but its only fact
    # is important, not critical.
    assert [need.id for need in missed_critical_needs(partial.client, analyse(partial))] == [
        "fund-gap"
    ]
    assert missed_critical_needs(complete.client, analyse(complete)) == []


def test_the_analysis_needs_a_wrap_up() -> None:
    session = make_session(client=Client.model_validate(coaching_client_data()))

    with pytest.raises(ValueError, match="no wrap-up"):
        analyse(session)


def test_a_need_completed_by_a_pitch_is_revealed_by_pitch_not_uncovered() -> None:
    session = interview(
        ("How do your customers pay?", ["cash-gap"], []),
        ("I'd suggest our Alpha Loan.", ["sharia"], ["sharia"]),
        recommend=[ALPHA],
    )

    analysis = analyse(session)

    fund_gap = analysis.needs[0]
    assert fund_gap.status == "revealed_by_pitch"
    assert fund_gap.via == Via(turn=3, question="I'd suggest our Alpha Loan.")
    assert (analysis.stats.needs_uncovered, analysis.stats.needs_after_pitch) == (0, 1)
    # It was found in full, so its suitable products still count as missed opportunities.
    assert [item.product_id for item in analysis.missed_opportunities] == [BETA]


def test_a_partly_found_need_stays_partial_even_after_a_pitch() -> None:
    session = interview(("I'd suggest our Alpha Loan.", ["sharia"], ["sharia"]), recommend=[ALPHA])

    fund_gap = analyse(session).needs[0]

    assert (fund_gap.status, fund_gap.via) == ("partial", None)


OVERDRAFT = "business-overdraft"
OVERDRAFT_PITCH = (
    "أقترح عليكِ السحب على المكشوف للأعمال: حد ائتماني مرن على حسابك التجاري، ولا تدفعين "
    "الفائدة إلا على ما تستخدمينه."
)


def test_an_unsuitable_product_the_client_had_already_ruled_out_says_when() -> None:
    # The manual test: "What do you need from the bank?" brought out her Sharia preference at
    # turn 5, she said it at turn 6, and the student pitched the overdraft at turn 7.
    session = real_interview(
        "noura-al-kuwari",
        ("مرحبًا نورة، حدّثيني عن عملك.", [], []),
        ("كيف تسير الأمور؟", [], []),
        ("ماذا تحتاجين من البنك؟", ["sharia-only"], []),
        (OVERDRAFT_PITCH, [], []),
        recommend=[OVERDRAFT],
        pitched={OVERDRAFT: [7]},
    )

    (verdict,) = analyse(session).products

    assert verdict.verdict == "unsuitable"
    assert (verdict.ruled_out_at, verdict.pitched_at) == (6, 7)


def test_a_fact_that_the_products_own_pitch_revealed_rules_nothing_out_beforehand() -> None:
    session = real_interview(
        "noura-al-kuwari",
        ("مرحبًا نورة، حدّثيني عن عملك.", [], []),
        (OVERDRAFT_PITCH, ["sharia-only"], ["sharia-only"]),
        recommend=[OVERDRAFT],
        pitched={OVERDRAFT: [3]},
    )

    (verdict,) = analyse(session).products

    assert (verdict.verdict, verdict.ruled_out_at, verdict.pitched_at) == ("unsuitable", None, None)


def test_a_fact_revealed_by_another_products_pitch_counts() -> None:
    session = real_interview(
        "noura-al-kuwari",
        ("I'd suggest our Invoice Advance.", ["sharia-only"], ["sharia-only"]),
        ("What about our Business Overdraft instead?", [], []),
        recommend=[OVERDRAFT],
        pitched={"invoice-advance": [1], OVERDRAFT: [3]},
    )

    (verdict,) = analyse(session).products

    assert (verdict.ruled_out_at, verdict.pitched_at) == (2, 3)


def test_an_unsuitable_product_that_no_fact_rules_out_says_nothing() -> None:
    # Murabaha is unsuitable for Rajesh (it finances goods), and no fact of his lists it.
    session = real_interview(
        "rajesh-menon",
        ("How do your clients pay you?", ["corporate-invoices"], []),
        recommend=["murabaha-working-capital"],
    )

    (verdict,) = analyse(session).products

    assert (verdict.verdict, verdict.ruled_out_at, verdict.pitched_at) == ("unsuitable", None, None)
