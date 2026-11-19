"""One failing fixture per validation rule; every error must name its file and field."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.content.loader import ContentValidationError
from app.content.registry import load_registry
from tests.content_factory import (
    ALPHA,
    BETA,
    CLIENT,
    SECRET_CASH_GAP,
    ContentDir,
    bank_data,
    client_data,
    product_data,
)

BANK_FILE = "content/bank.yaml"
PRODUCT_FILE = f"content/products/{ALPHA}.yaml"
CLIENT_FILE = f"content/clients/{CLIENT}.yaml"

Change = Callable[[dict[str, Any]], None]


def errors_for(content: ContentDir) -> list[str]:
    with pytest.raises(ContentValidationError) as caught:
        load_registry(content.root)
    return caught.value.messages


def change_bank(change: Change) -> Callable[[ContentDir], None]:
    def apply(content: ContentDir) -> None:
        data = bank_data()
        change(data)
        content.write("bank.yaml", data)

    return apply


def change_product(change: Change) -> Callable[[ContentDir], None]:
    def apply(content: ContentDir) -> None:
        data = product_data()
        change(data)
        content.write(f"products/{ALPHA}.yaml", data)

    return apply


def change_client(change: Change) -> Callable[[ContentDir], None]:
    def apply(content: ContentDir) -> None:
        data = client_data()
        change(data)
        content.write(f"clients/{CLIENT}.yaml", data)

    return apply


def fact(index: int, **values: Any) -> Change:
    return lambda data: data["hidden_facts"][index].update(values)


def need(index: int, **values: Any) -> Change:
    return lambda data: data["needs"][index].update(values)


def set_(key: str, value: Any) -> Change:
    return lambda data: data.update({key: value})


def drop(*keys: str | int) -> Change:
    def apply(data: dict[str, Any]) -> None:
        target: Any = data
        for key in keys[:-1]:
            target = target[key]
        del target[keys[-1]]

    return apply


def extra_fact(count: int) -> Change:
    def apply(data: dict[str, Any]) -> None:
        template = data["hidden_facts"][1]
        for n in range(count):
            data["hidden_facts"].append({**template, "id": f"extra-{n}", "requires": []})

    return apply


# (file, field, part of the message, how to break the sample content)
RULES: dict[str, tuple[str, str, str, Callable[[ContentDir], None]]] = {
    # bank.yaml
    "bank name missing": (BANK_FILE, "name", "Field required", change_bank(drop("name"))),
    "bank English empty": (
        BANK_FILE,
        "name.en",
        "at least 1 character",
        change_bank(set_("name", {"en": " ", "ar": "بنك"})),
    ),
    "currency not QAR": (BANK_FILE, "currency", "'QAR'", change_bank(set_("currency", "USD"))),
    "bank unknown key": (BANK_FILE, "website", "Extra inputs", change_bank(set_("website", "x"))),
    "text of the wrong type": (
        BANK_FILE,
        "tagline",
        "Input should be text, or a mapping",
        change_bank(set_("tagline", ["x"])),
    ),
    # products
    "product id not a slug": (
        PRODUCT_FILE,
        "id",
        "should match pattern",
        change_product(set_("id", "Alpha_Loan")),
    ),
    "product id not the file name": (
        PRODUCT_FILE,
        "id",
        "must match the file name: 'alpha-loan'",
        change_product(set_("id", "gamma-loan")),
    ),
    "schema version": (
        PRODUCT_FILE,
        "schema_version",
        "Input should be 1",
        change_product(set_("schema_version", 2)),
    ),
    "no segments": (
        PRODUCT_FILE,
        "segments",
        "at least 1 item",
        change_product(set_("segments", [])),
    ),
    "unknown segment": (
        PRODUCT_FILE,
        "segments[0]",
        "'retail' or 'sme'",
        change_product(set_("segments", ["corporate"])),
    ),
    "unknown category": (
        PRODUCT_FILE,
        "category",
        "Input should be",
        change_product(set_("category", "loan")),
    ),
    "Sharia-compliant and interest-based": (
        PRODUCT_FILE,
        "interest_based",
        "can't be both",
        change_product(set_("sharia_compliant", True)),
    ),
    "one feature": (
        PRODUCT_FILE,
        "features",
        "at least 2 items",
        change_product(set_("features", ["x"])),
    ),
    "one limitation": (
        PRODUCT_FILE,
        "limitations",
        "at least 2 items",
        change_product(set_("limitations", ["x"])),
    ),
    "no eligibility": (
        PRODUCT_FILE,
        "eligibility",
        "at least 1 item",
        change_product(set_("eligibility", [])),
    ),
    "pricing not marked fictional": (
        PRODUCT_FILE,
        "pricing",
        '"(fictional)"',
        change_product(set_("pricing", "5% a year")),
    ),
    "client view missing": (
        PRODUCT_FILE,
        "client_view",
        "Field required",
        change_product(drop("client_view")),
    ),
    "Arabic empty": (
        PRODUCT_FILE,
        "summary.ar",
        "at least 1 character",
        change_product(set_("summary", {"en": "A loan.", "ar": ""})),
    ),
    # clients: fields
    "client id not the file name": (
        CLIENT_FILE,
        "id",
        "must match the file name: 'test-client'",
        change_client(set_("id", "other-client")),
    ),
    "unknown client segment": (
        CLIENT_FILE,
        "segment",
        "Input should be",
        change_client(set_("segment", "corp")),
    ),
    "unknown difficulty": (
        CLIENT_FILE,
        "difficulty",
        "'easy', 'medium' or 'hard'",
        change_client(set_("difficulty", "expert")),
    ),
    "opening line missing": (
        CLIENT_FILE,
        "card.opening_line",
        "Field required",
        change_client(drop("card", "opening_line")),
    ),
    "age not a number": (
        CLIENT_FILE,
        "persona.age",
        "valid integer",
        change_client(lambda data: data["persona"].update(age="forty")),
    ),
    "unknown financial knowledge": (
        CLIENT_FILE,
        "persona.financial_knowledge",
        "'low', 'medium' or 'high'",
        change_client(lambda data: data["persona"].update(financial_knowledge="expert")),
    ),
    "no open facts": (
        CLIENT_FILE,
        "open_facts",
        "at least 1 item",
        change_client(set_("open_facts", [])),
    ),
    "seven open facts": (
        CLIENT_FILE,
        "open_facts",
        "at most 6 items",
        change_client(set_("open_facts", [f"fact {n}" for n in range(7)])),
    ),
    "one hidden fact": (
        CLIENT_FILE,
        "hidden_facts",
        "at least 2 items",
        change_client(lambda data: data["hidden_facts"].pop()),
    ),
    "nine hidden facts": (
        CLIENT_FILE,
        "hidden_facts",
        "at most 8 items",
        change_client(extra_fact(7)),
    ),
    "fact id not a slug": (
        CLIENT_FILE,
        "hidden_facts[0].id",
        "should match pattern",
        change_client(fact(0, id="Cash Gap")),
    ),
    "no unlock behaviours": (
        CLIENT_FILE,
        "hidden_facts[1].unlock_when",
        "at least 1 item",
        change_client(fact(1, unlock_when=[])),
    ),
    "unknown importance": (
        CLIENT_FILE,
        "hidden_facts[0].importance",
        "'critical', 'important' or 'minor'",
        change_client(fact(0, importance="huge")),
    ),
    "no example questions": (
        CLIENT_FILE,
        "hidden_facts[0].example_questions",
        "at least 1 item",
        change_client(fact(0, example_questions=[])),
    ),
    "no needs": (CLIENT_FILE, "needs", "at least 1 item", change_client(set_("needs", []))),
    "no evidence facts": (
        CLIENT_FILE,
        "needs[0].evidence_facts",
        "at least 1 item",
        change_client(need(0, evidence_facts=[])),
    ),
    "no catalogue fit without a referral note": (
        CLIENT_FILE,
        "referral_note",
        "required when no_catalogue_fit is true",
        change_client(set_("no_catalogue_fit", True)),
    ),
    "one key question": (
        CLIENT_FILE,
        "coach_notes.key_questions",
        "at least 2 items",
        change_client(lambda data: data["coach_notes"].update(key_questions=["one?"])),
    ),
    "coach notes missing": (
        CLIENT_FILE,
        "coach_notes",
        "Field required",
        change_client(drop("coach_notes")),
    ),
    # clients: cross-checks in the registry
    "duplicate fact id": (
        CLIENT_FILE,
        "hidden_facts[1].id",
        "duplicate id 'cash-gap'",
        change_client(fact(1, id="cash-gap", requires=[])),
    ),
    "duplicate need id": (
        CLIENT_FILE,
        "needs[1].id",
        "duplicate id 'fund-gap'",
        change_client(lambda data: data["needs"].append(dict(data["needs"][0]))),
    ),
    "unknown suitable product": (
        CLIENT_FILE,
        "needs[0].suitable_products[0]",
        "unknown product 'no-such-product'",
        change_client(need(0, suitable_products=["no-such-product"])),
    ),
    "unknown unsuitable product": (
        CLIENT_FILE,
        "needs[0].unsuitable_products[0].id",
        "unknown product 'no-such-product'",
        change_client(need(0, unsuitable_products=[{"id": "no-such-product", "reason": "x"}])),
    ),
    "unknown pitched product": (
        CLIENT_FILE,
        "hidden_facts[0].unlock_on_product_pitch[0]",
        "unknown product 'no-such-product'",
        change_client(fact(0, unlock_on_product_pitch=["no-such-product"])),
    ),
    "requires an unknown fact": (
        CLIENT_FILE,
        "hidden_facts[1].requires[0]",
        "unknown hidden fact 'ghost'",
        change_client(fact(1, requires=["ghost"])),
    ),
    "evidence is an unknown fact": (
        CLIENT_FILE,
        "needs[0].evidence_facts[0]",
        "unknown hidden fact 'ghost'",
        change_client(need(0, evidence_facts=["ghost"])),
    ),
    "requires cycle": (
        CLIENT_FILE,
        "hidden_facts[0].requires",
        "circular requirement: cash-gap → expansion → cash-gap",
        change_client(fact(0, requires=["expansion"])),
    ),
    "fact requires itself": (
        CLIENT_FILE,
        "hidden_facts[0].requires",
        "circular requirement: cash-gap → cash-gap",
        change_client(fact(0, requires=["cash-gap"])),
    ),
    "suitable and unsuitable for one need": (
        CLIENT_FILE,
        "needs[0].unsuitable_products[0].id",
        f"'{ALPHA}' is also listed in suitable_products",
        change_client(need(0, unsuitable_products=[{"id": ALPHA, "reason": "x"}])),
    ),
    "duplicate unsuitable product": (
        CLIENT_FILE,
        "needs[0].unsuitable_products[1].id",
        f"duplicate id '{BETA}'",
        change_client(
            need(0, unsuitable_products=[{"id": BETA, "reason": "x"}, {"id": BETA, "reason": "y"}])
        ),
    ),
    "need without a suitable product": (
        CLIENT_FILE,
        "needs[0].suitable_products",
        "list at least one product",
        change_client(need(0, suitable_products=[])),
    ),
    "no critical fact": (
        CLIENT_FILE,
        "hidden_facts",
        "importance: critical",
        change_client(fact(0, importance="important")),
    ),
}


@pytest.mark.parametrize("rule", RULES)
def test_each_rule_names_the_file_and_the_field(content: ContentDir, rule: str) -> None:
    path, where, fragment, break_it = RULES[rule]
    break_it(content)

    errors = errors_for(content)

    prefix = f"{path} › {where}: "
    matching = [error for error in errors if error.startswith(prefix)]
    assert matching, f"no error starts with {prefix!r}: {errors}"
    assert any(fragment in error for error in matching), errors


def test_the_error_format_matches_the_spec(content: ContentDir) -> None:
    change_client(drop("hidden_facts", 1, "unlock_when"))(content)
    assert errors_for(content) == [f"{CLIENT_FILE} › hidden_facts[1].unlock_when: Field required"]


def test_a_client_with_no_catalogue_fit_may_list_no_suitable_products(content: ContentDir) -> None:
    change_client(
        lambda data: data.update(
            no_catalogue_fit=True,
            referral_note="Refer to the trade-finance team.",
            needs=[{**data["needs"][0], "suitable_products": []}],
        )
    )(content)
    assert load_registry(content.root).get_client(CLIENT).no_catalogue_fit is True


@pytest.mark.parametrize(
    ("text", "where", "fragment"),
    [
        ("id: test-client\nname: a: b\n", "line 2, column 8", "mapping values are not allowed"),
        ("id: test-client\nid: test-client\n", "line 2, column 1", "duplicate key 'id'"),
    ],
)
def test_yaml_errors_give_the_line_and_column(
    content: ContentDir, text: str, where: str, fragment: str
) -> None:
    content.write_text(f"clients/{CLIENT}.yaml", text)
    [error] = errors_for(content)
    assert error.startswith(f"{CLIENT_FILE} › {where}: ")
    assert fragment in error


@pytest.mark.parametrize(
    ("relative", "write", "expected"),
    [
        (f"clients/{CLIENT}.yaml", "", f"{CLIENT_FILE}: is empty"),
        (f"clients/{CLIENT}.yaml", "- a\n- b\n", f"{CLIENT_FILE}: should be a mapping"),
        ("clients/other.yml", "id: other\n", "content/clients/other.yml: rename it to .yaml"),
    ],
)
def test_file_level_problems(content: ContentDir, relative: str, write: str, expected: str) -> None:
    content.write_text(relative, write)
    assert any(error.startswith(expected) for error in errors_for(content))


def test_text_that_is_not_utf8_is_reported(content: ContentDir) -> None:
    content.path(f"clients/{CLIENT}.yaml").write_bytes(b"id: \xff\xfe\n")
    assert errors_for(content) == [f"{CLIENT_FILE}: is not valid UTF-8 text"]


def test_missing_bank_file_and_folder_are_reported(content: ContentDir) -> None:
    content.remove("bank.yaml")
    content.remove(f"clients/{CLIENT}.yaml")
    content.path("clients").rmdir()
    assert errors_for(content) == [
        f"{BANK_FILE}: file not found",
        "content/clients: folder not found",
    ]


def test_a_missing_content_folder_is_reported(tmp_path: Path) -> None:
    with pytest.raises(ContentValidationError) as caught:
        load_registry(tmp_path / "nowhere")
    assert caught.value.messages == ["nowhere: folder not found"]


def test_templates_and_hidden_files_are_ignored(content: ContentDir) -> None:
    content.write_text("clients/_template.yaml", "this: [is not valid\n")
    content.write_text("clients/.gitkeep", "")
    content.write_text("products/README.md", "# notes\n")
    assert [client.id for client in load_registry(content.root).list_clients()] == [CLIENT]


def test_every_error_in_every_file_is_collected_and_grouped_by_file(content: ContentDir) -> None:
    change_bank(set_("currency", "USD"))(content)
    change_product(set_("features", ["x"]))(content)
    change_client(lambda data: data.update(difficulty="expert", open_facts=[]))(content)

    errors = errors_for(content)

    assert [error.split(" › ")[0] for error in errors] == [
        BANK_FILE,
        CLIENT_FILE,
        CLIENT_FILE,
        PRODUCT_FILE,
    ]


def test_a_broken_product_does_not_cascade_into_its_clients(content: ContentDir) -> None:
    change_product(set_("category", "loan"))(content)
    errors = errors_for(content)
    assert len(errors) == 1 and errors[0].startswith(f"{PRODUCT_FILE} › category: ")


def test_errors_never_quote_private_content(content: ContentDir) -> None:
    # A YAML syntax error on a hidden-fact line, and a rejected value that is private text.
    broken = client_data()
    broken["hidden_facts"][1]["importance"] = SECRET_CASH_GAP
    content.write(f"clients/{CLIENT}.yaml", broken)
    content.write_text("clients/second.yaml", f"id: second\ncontent: {SECRET_CASH_GAP}\n")

    with pytest.raises(ContentValidationError) as caught:
        load_registry(content.root)

    assert "SECRET" not in str(caught.value)
    assert any("line 2" in error for error in caught.value.messages)
