import json
from collections.abc import Collection

import pytest

from app.content import Client, load_registry
from app.llm import InvalidOutput, ModelTimeout, Role
from app.llm.fake import FakeLLM, Scripted
from app.prompts import PROMPT_VERSION
from app.simulation.disclosure import GateOutcome, eligible_facts, run_gate
from tests.content_factory import ALPHA, BETA
from tests.interview_factory import REPO_CONTENT, client_with, gate_reply, hidden_fact, registry

PRODUCTS = registry().list_products()

CHAIN = client_with(
    hidden_fact("cash-gap", signal="SIGNAL-CASH-GAP"),
    hidden_fact("expansion", importance="important", requires=["cash-gap"], pitch=[ALPHA]),
    hidden_fact("pitch-reaction", importance="minor", pitch=[ALPHA]),
)


async def gate(
    reply: Scripted,
    *,
    client: Client = CHAIN,
    unlocked: Collection[str] = (),
    max_unlocks: int = 2,
    llm: FakeLLM | None = None,
) -> GateOutcome:
    fake = llm or FakeLLM()
    fake.script(Role.GATE, reply)
    return await run_gate(
        fake,
        model="gate-model",
        client=client,
        products=PRODUCTS,
        unlocked=unlocked,
        client_reply="Hello, I have a few minutes.",
        student_message="How do your customers pay you?",
        max_unlocks=max_unlocks,
    )


def test_eligible_facts_are_locked_facts_whose_requirements_are_unlocked() -> None:
    assert [f.id for f in eligible_facts(CHAIN, set())] == ["cash-gap", "pitch-reaction"]
    assert [f.id for f in eligible_facts(CHAIN, {"cash-gap"})] == ["expansion", "pitch-reaction"]
    assert eligible_facts(CHAIN, {"cash-gap", "expansion", "pitch-reaction"}) == []


async def test_ids_outside_the_eligible_set_are_dropped() -> None:
    outcome = await gate(gate_reply("made-up", "expansion", "cash-gap", "cash-gap"))

    assert outcome.unlocked == ("cash-gap",)  # expansion still requires cash-gap
    assert not outcome.failed


async def test_a_fact_that_becomes_eligible_this_turn_waits_for_the_next_turn() -> None:
    # cash-gap unlocks now; expansion, which requires it, may not unlock in the same turn,
    # not even through its product pitch.
    outcome = await gate(gate_reply("cash-gap", "expansion", products=[ALPHA]))

    assert outcome.unlocked == ("cash-gap", "pitch-reaction")
    assert "expansion" not in outcome.unlocked


async def test_unlocks_above_the_cap_are_trimmed_by_importance() -> None:
    client = client_with(
        hidden_fact("minor-fact", importance="minor"),
        hidden_fact("important-fact", importance="important"),
        hidden_fact("critical-fact"),
    )

    outcome = await gate(
        gate_reply("minor-fact", "important-fact", "critical-fact"), client=client, max_unlocks=2
    )

    assert outcome.unlocked == ("important-fact", "critical-fact")  # content order


async def test_ties_in_importance_keep_the_content_order() -> None:
    client = client_with(hidden_fact("first"), hidden_fact("second"))

    outcome = await gate(gate_reply("second", "first"), client=client, max_unlocks=1)

    assert outcome.unlocked == ("first",)


async def test_a_pitched_product_unlocks_its_facts_deterministically_beyond_the_cap() -> None:
    outcome = await gate(gate_reply("cash-gap", products=[ALPHA]), max_unlocks=1)

    assert outcome.unlocked == ("cash-gap", "pitch-reaction")
    assert outcome.by_pitch == ("pitch-reaction",)
    assert outcome.products_mentioned == (ALPHA,)


async def test_a_pitch_alone_unlocks_without_the_gate_choosing_the_fact() -> None:
    outcome = await gate(gate_reply(products=[ALPHA]))
    assert outcome.unlocked == ("pitch-reaction",)


async def test_unknown_and_repeated_product_ids_are_dropped() -> None:
    outcome = await gate(gate_reply(products=["nope", BETA, BETA]))

    assert outcome.products_mentioned == (BETA,)
    assert outcome.unlocked == ()  # nothing reacts to the deposit


@pytest.mark.parametrize(
    "reply",
    [
        "not json at all",
        '{"unlocked": "cash-gap"}',
        '{"note": "asks how they pay", "unlocked": ["cash-gap"], "products_mentioned": []}',
        InvalidOutput("unusable JSON after one retry"),
        ModelTimeout("slow"),
    ],
    ids=["malformed", "wrong-shape", "unlock-without-evidence", "invalid-output", "timeout"],
)
async def test_a_failed_gate_unlocks_nothing_and_mentions_no_product(reply: Scripted) -> None:
    outcome = await gate(reply)

    assert outcome.failed
    assert outcome.unlocked == () and outcome.products_mentioned == ()
    assert outcome.eligible == ("cash-gap", "pitch-reaction")


async def test_a_long_note_is_shortened_rather_than_failing_the_gate() -> None:
    outcome = await gate(gate_reply("cash-gap", note="x" * 500))

    assert not outcome.failed
    assert outcome.note == "x" * 200


async def test_the_gate_gets_ids_conditions_and_the_catalogue_and_nothing_else() -> None:
    fake = FakeLLM()
    await gate(gate_reply(), llm=fake)

    [call] = fake.calls_for(Role.GATE)
    assert call.method == "chat_json"
    assert (call.model, call.temperature, call.max_tokens) == ("gate-model", 0, 200)
    assert call.prompt_version == PROMPT_VERSION["gate"]
    system, user = call.messages
    assert (system.role, user.role) == ("system", "user")
    data = json.loads(user.content)
    assert set(data) == {"client_reply", "student_message", "eligible_facts", "catalogue"}
    assert data["eligible_facts"] == [
        {"id": "cash-gap", "unlock_when": ["asks about cash-gap"]},
        {"id": "pitch-reaction", "unlock_when": ["asks about pitch-reaction"]},
    ]
    assert data["catalogue"][0] == {
        "id": ALPHA,
        "name_en": "Alpha Loan",
        "name_ar": None,
        "interest_based": True,
        "sharia_compliant": False,
    }
    for fact in CHAIN.hidden_facts:
        assert fact.content not in system.content + user.content


async def test_an_unlock_quoting_its_own_behaviour_is_kept_ignoring_case_and_spaces() -> None:
    outcome = await gate(gate_reply(("cash-gap", "  Asks About CASH-GAP ")))

    assert outcome.unlocked == ("cash-gap",)
    assert outcome.rejected == ()
    assert outcome.quotes == {"cash-gap": "Asks About CASH-GAP"}


async def test_an_unlock_quoting_another_facts_behaviour_is_rejected() -> None:
    outcome = await gate(gate_reply(("pitch-reaction", "asks about cash-gap")))

    assert outcome.unlocked == ()
    assert outcome.rejected == ("pitch-reaction",)


async def test_an_unlock_with_an_invented_behaviour_is_rejected() -> None:
    outcome = await gate(gate_reply(("cash-gap", "asks how the business is going")))

    assert outcome.unlocked == ()
    assert outcome.rejected == ("cash-gap",)


async def test_rejected_unlocks_do_not_use_up_the_cap() -> None:
    client = client_with(hidden_fact("first"), hidden_fact("second"))

    outcome = await gate(gate_reply(("first", "made up"), "second"), client=client, max_unlocks=1)

    assert outcome.unlocked == ("second",)
    assert outcome.rejected == ("first",)


async def test_one_good_quote_is_enough_when_a_fact_is_listed_twice() -> None:
    outcome = await gate(gate_reply(("cash-gap", "made up"), "cash-gap"))

    assert outcome.unlocked == ("cash-gap",)
    assert outcome.rejected == ()


async def test_a_misquoted_fact_unlocked_by_a_pitch_is_not_reported_as_rejected() -> None:
    outcome = await gate(gate_reply(("pitch-reaction", "made up"), products=[ALPHA]))

    assert outcome.by_pitch == ("pitch-reaction",)
    assert outcome.rejected == ()


async def test_a_payment_follow_up_cannot_unlock_the_big_contract() -> None:
    # The manual test: once late-payments was unlocked, "Has that ever made it hard to pay
    # your staff?" unlocked big-contract, with a note about payment delays. Quoting one of
    # late-payments' behaviours for big-contract is now rejected.
    noura = load_registry(REPO_CONTENT).get_client("noura-al-kuwari")
    late_payments = next(fact for fact in noura.hidden_facts if fact.id == "late-payments")

    outcome = await gate(
        gate_reply(("big-contract", late_payments.unlock_when[1])),
        client=noura,
        unlocked={"late-payments"},
    )

    assert outcome.eligible == ("sharia-only", "big-contract")
    assert outcome.unlocked == ()
    assert outcome.rejected == ("big-contract",)
