"""evals/scenarios.py builds the M7 scripts from the content, with no model calls."""

from typing import Any

from evals.scenarios import (
    ARABIC_LINES,
    ATTACKS,
    SCRIPTS,
    Scenario,
    ScriptName,
    build,
    build_all,
    dependency_order,
)

from app.content import Client, load_registry
from tests.content_factory import BETA
from tests.interview_factory import REPO_CONTENT, client_data_with, hidden_fact

CONTENT = load_registry(REPO_CONTENT)
PRODUCTS = {product.id: product for product in CONTENT.list_products()}


def scenario(client_id: str, script: ScriptName) -> Scenario:
    return build(CONTENT.get_client(client_id), script, PRODUCTS)


def test_weak_pitches_the_first_unsuitable_product_of_the_first_need_that_has_one() -> None:
    pitched = {client.id: scenario(client.id, "weak").pitched for client in CONTENT.list_clients()}

    # Ahmed's first need has no unsuitable product, so his pitch comes from `car-later`.
    assert pitched == {
        "fatima-al-sulaiti": "salary-personal-finance",
        "rajesh-menon": "business-overdraft",
        "ahmed-hassan": "salary-personal-finance",
        "noura-al-kuwari": "business-overdraft",
        "khalid-al-marri": "business-overdraft",
    }


def test_weak_allows_only_the_facts_that_react_to_the_pitch_and_only_at_the_pitch() -> None:
    weak = scenario("ahmed-hassan", "weak")

    assert [line.kind for line in weak.lines] == [*["generic"] * 4, "pitch", "follow_up"]
    assert weak.lines[1].text == "How is work going at the moment?"  # retail: work
    assert weak.lines[4].text == "I'd suggest our Personal Loan (Salary Transfer)."
    assert weak.lines[5].text == "So would that work for you?"
    assert (dict(weak.expected), dict(weak.allowed)) == ({}, {"existing-loan": (4,)})
    assert weak.wrapup is not None
    assert weak.wrapup.needs_summary == "The client wants better banking services."
    assert [item.product_id for item in weak.wrapup.recommendations] == ["salary-personal-finance"]
    assert (weak.language, weak.coach_language) == ("en", "en")
    assert scenario("noura-al-kuwari", "weak").lines[1].text == (
        "How is business going at the moment?"
    )


def test_arabic_weak_uses_the_fixed_arabic_lines_and_the_products_arabic_name() -> None:
    arabic = scenario("noura-al-kuwari", "arabic-weak")

    assert [line.text for line in arabic.lines] == [
        *ARABIC_LINES,
        "أقترح عليك السحب على المكشوف للأعمال.",
        "هل يناسبك ذلك؟",
    ]
    assert dict(arabic.allowed) == {"sharia-only": (4,)}
    assert (arabic.language, arabic.coach_language) == ("ar", "ar")
    assert arabic.wrapup is not None
    assert arabic.wrapup.needs_summary == "يريد العميل خدمات مصرفية أفضل."
    assert [item.product_id for item in arabic.wrapup.recommendations] == ["business-overdraft"]


def test_strong_asks_each_fact_in_dependency_order_and_accepts_one_turn_early() -> None:
    strong = scenario("khalid-al-marri", "strong")

    assert [line.kind for line in strong.lines] == ["opener", *["probe"] * 4, "pitch"]
    assert strong.lines[0].text == (
        "Thanks for coming in. Could you tell me a bit about your situation?"
    )
    assert strong.lines[1].text == "Does the company need any new vehicles or equipment?"
    assert dict(strong.expected) == {
        "needs-trucks": (0, 1),
        "sharia-on-pitch": (1, 2),
        "brother-exit": (2, 3),
        "seasonal-peaks": (3, 4),
    }
    assert strong.lines[-1].text == "I'd suggest our Ijara Asset Finance."
    assert strong.allowed == {}


def test_strong_lists_every_need_and_recommends_each_suitable_product_once() -> None:
    # Fatima's two needs share the Wakala deposit, and Noura's the Murabaha: the API
    # rejects a product recommended twice.
    recommended = {
        client.id: [item.product_id for item in wrapup.recommendations]
        for client in CONTENT.list_clients()
        if (wrapup := scenario(client.id, "strong").wrapup) is not None
    }

    assert recommended == {
        "fatima-al-sulaiti": ["wakala-term-deposit"],
        "rajesh-menon": ["invoice-advance"],
        "ahmed-hassan": ["multicurrency-remit-account", "ijara-asset-finance"],
        "noura-al-kuwari": ["murabaha-working-capital"],
        "khalid-al-marri": ["ijara-asset-finance", "murabaha-working-capital"],
    }
    fatima = CONTENT.get_client("fatima-al-sulaiti")
    wrapup = scenario(fatima.id, "strong").wrapup
    assert wrapup is not None
    assert all(need.description.en in wrapup.needs_summary for need in fatima.needs)


def test_a_fact_comes_after_the_facts_it_requires_whatever_the_content_order() -> None:
    client = Client.model_validate(
        client_data_with(
            hidden_fact("expansion", importance="important", requires=["cash-gap"]),
            hidden_fact("cash-gap"),
            hidden_fact("sharia"),
        )
    )

    assert [fact.id for fact in dependency_order(client)] == ["cash-gap", "expansion", "sharia"]


def test_adversarial_is_five_attacks_with_nothing_expected_and_no_coach() -> None:
    attacks = scenario("rajesh-menon", "adversarial")

    assert [line.text for line in attacks.lines] == list(ATTACKS)
    assert (attacks.expected, attacks.allowed, attacks.wrapup, attacks.coach_language) == (
        {},
        {},
        None,
        None,
    )


def test_without_an_unsuitable_or_suitable_product_there_is_no_pitch_and_no_wrapup() -> None:
    data: dict[str, Any] = client_data_with(hidden_fact("cash-gap"), hidden_fact("sharia"))
    data["needs"][0]["suitable_products"] = []
    data["needs"][0]["unsuitable_products"] = []
    client = Client.model_validate(data)
    products = {BETA: PRODUCTS["wakala-term-deposit"]}

    weak = build(client, "weak", products)
    strong = build(client, "strong", products)

    assert [line.kind for line in weak.lines] == [*["generic"] * 4, "follow_up"]
    assert (weak.pitched, weak.wrapup, weak.coach_language) == (None, None, None)
    assert [line.kind for line in strong.lines] == ["opener", "probe", "probe"]
    assert (strong.wrapup, strong.coach_language) == (None, None)


def test_build_all_runs_each_client_through_the_scripts_in_turn() -> None:
    keys = [s.key for s in build_all(CONTENT, ["noura-al-kuwari", "rajesh-menon"], SCRIPTS)]

    assert keys == [
        "noura-al-kuwari--strong",
        "noura-al-kuwari--weak",
        "noura-al-kuwari--adversarial",
        "noura-al-kuwari--arabic-weak",
        "rajesh-menon--strong",
        "rajesh-menon--weak",
        "rajesh-menon--adversarial",
        "rajesh-menon--arabic-weak",
    ]
