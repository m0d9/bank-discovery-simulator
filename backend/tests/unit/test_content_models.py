from typing import Any

import pytest
from pydantic import ValidationError

from app.content.models import Client, LocalizedText, Product
from tests.content_factory import client_data, product_data


def error_locs(exc: ValidationError) -> list[tuple[int | str, ...]]:
    return [tuple(error["loc"]) for error in exc.errors()]


def test_a_plain_string_is_english_only_and_whitespace_is_stripped() -> None:
    assert LocalizedText.model_validate("  Hello\n") == LocalizedText(en="Hello", ar=None)
    text = LocalizedText.model_validate({"en": "Hello", "ar": " مرحبًا "})
    assert (text.en, text.ar) == ("Hello", "مرحبًا")


@pytest.mark.parametrize("value", [5, ["Hello"], None])
def test_localized_text_rejects_anything_but_text_or_a_mapping(value: Any) -> None:
    with pytest.raises(ValidationError) as caught:
        LocalizedText.model_validate(value)
    assert "Input should be text, or a mapping" in str(caught.value)


@pytest.mark.parametrize(
    "value", [{"en": ""}, {"en": "   "}, {"ar": "مرحبًا"}, {"en": "x", "ar": ""}]
)
def test_localized_text_needs_non_empty_english_and_non_empty_arabic_when_given(
    value: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        LocalizedText.model_validate(value)


def test_localized_text_schema_accepts_a_string_or_a_mapping() -> None:
    schema = Product.model_json_schema()["$defs"]["LocalizedText"]
    string_form, mapping_form = schema["anyOf"]
    assert string_form == {"type": "string", "minLength": 1}
    assert mapping_form["required"] == ["en"]
    assert mapping_form["additionalProperties"] is False


def test_unknown_keys_are_rejected_everywhere() -> None:
    data = client_data()
    data["persona"]["favourite_food"] = "machboos"
    with pytest.raises(ValidationError) as caught:
        Client.model_validate(data)
    assert error_locs(caught.value) == [("persona", "favourite_food")]


def test_a_product_cannot_be_both_sharia_compliant_and_interest_based() -> None:
    with pytest.raises(ValidationError) as caught:
        Product.model_validate(product_data(sharia_compliant=True, interest_based=True))
    assert error_locs(caught.value) == [("interest_based",)]


def test_pricing_must_be_marked_fictional_in_english() -> None:
    with pytest.raises(ValidationError) as caught:
        Product.model_validate(product_data(pricing={"en": "5% a year", "ar": "5% سنويًا"}))
    assert error_locs(caught.value) == [("pricing",)]


def test_referral_note_is_required_only_without_a_catalogue_fit() -> None:
    with pytest.raises(ValidationError) as caught:
        Client.model_validate(client_data(no_catalogue_fit=True))
    assert error_locs(caught.value) == [("referral_note",)]

    referred = Client.model_validate(
        client_data(no_catalogue_fit=True, referral_note="Refer to the trade-finance team.")
    )
    assert referred.referral_note == LocalizedText(en="Refer to the trade-finance team.")
    assert Client.model_validate(client_data()).referral_note is None


def test_the_answer_key_text_shown_with_the_feedback_may_have_arabic() -> None:
    data = client_data(
        no_catalogue_fit=True,
        referral_note={"en": "Refer to trade finance.", "ar": "الإحالة إلى التمويل التجاري."},
    )
    data["needs"][0]["description"] = {"en": "Bridge the gap.", "ar": "سدّ الفجوة."}
    data["needs"][0]["unsuitable_products"][0]["reason"] = {"en": "No loan.", "ar": "لا قرض."}

    need = Client.model_validate(data).needs[0]

    assert need.description == LocalizedText(en="Bridge the gap.", ar="سدّ الفجوة.")
    assert need.unsuitable_products[0].reason.ar == "لا قرض."
    assert Client.model_validate(data).referral_note == LocalizedText(
        en="Refer to trade finance.", ar="الإحالة إلى التمويل التجاري."
    )
    # Plain strings stay valid, as English only.
    plain = Client.model_validate(client_data()).needs[0]
    assert plain.description == LocalizedText(en="Bridge the gap until customers pay.")


def test_valid_models_fill_their_defaults() -> None:
    client = Client.model_validate(client_data())
    assert client.no_catalogue_fit is False
    assert client.persona.family is None
    assert client.hidden_facts[0].unlock_on_product_pitch == []
    assert client.hidden_facts[0].requires == []
    assert Product.model_validate(product_data()).name == LocalizedText(en="Alpha Loan")


@pytest.mark.parametrize("gender", [None, "other", "Female"])
def test_a_persona_needs_a_grammatical_gender(gender: str | None) -> None:
    data = client_data()
    if gender is None:
        del data["persona"]["gender"]
    else:
        data["persona"]["gender"] = gender

    with pytest.raises(ValidationError) as caught:
        Client.model_validate(data)

    assert error_locs(caught.value) == [("persona", "gender")]
