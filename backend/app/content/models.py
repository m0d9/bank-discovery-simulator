"""The content schema: what the YAML files under `content/` may contain.

Every model forbids unknown keys, so a misspelt field is an error instead of being ignored.
Checks that span several facts, needs or files live in `registry.py`.
"""

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetJsonSchemaHandler,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, PydanticCustomError

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
FICTIONAL_MARKER = "(fictional)"

Slug = Annotated[str, StringConstraints(pattern=SLUG_PATTERN)]
# Stripped because YAML block scalars keep a trailing newline.
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

Segment = Literal["retail", "sme"]
Category = Literal["financing", "deposit", "account", "transfer"]
Difficulty = Literal["easy", "medium", "hard"]
Importance = Literal["critical", "important", "minor"]
FinancialKnowledge = Literal["low", "medium", "high"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_attribute_docstrings=True)


class LocalizedText(_Strict):
    """Text in English (required) and Arabic (optional). A plain string means English only."""

    en: Text
    """English text."""
    ar: Text | None = None
    """Arabic text, in Modern Standard Arabic."""

    @model_validator(mode="before")
    @classmethod
    def _plain_string_is_english(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"en": data}
        if isinstance(data, dict | LocalizedText):
            return data
        raise PydanticCustomError(
            "localized_text", "Input should be text, or a mapping with `en` and optionally `ar`"
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        # Editors must accept both forms the validator accepts: "text" and {en, ar}.
        schema = handler.resolve_ref_schema(handler(core_schema))
        mapping = dict(schema)
        schema.clear()
        schema["description"] = mapping.pop("description", "")
        schema["anyOf"] = [{"type": "string", "minLength": 1}, mapping]
        return schema


class Bank(_Strict):
    """The fictional bank (`content/bank.yaml`)."""

    name: LocalizedText
    """The bank's name, shown in the page header."""
    tagline: LocalizedText
    """A short slogan."""
    disclaimer: LocalizedText
    """Shown in the footer: the bank and its products are fictional and for teaching only."""
    currency: Literal["QAR"]
    """Every amount in the content is in Qatari riyals."""


class Product(_Strict):
    """One product in the catalogue (`content/products/<id>.yaml`)."""

    id: Slug
    """Lowercase words joined by hyphens. Must equal the file name without `.yaml`."""
    schema_version: Literal[1]
    name: LocalizedText
    summary: LocalizedText
    """One or two sentences describing the product."""
    segments: list[Segment] = Field(min_length=1)
    """Who can have it: `retail` (individuals) and/or `sme` (small and medium businesses)."""
    category: Category
    sharia_compliant: bool
    interest_based: bool
    """True for conventional products that charge interest. Never true with `sharia_compliant`."""
    features: list[LocalizedText] = Field(min_length=2)
    limitations: list[LocalizedText] = Field(min_length=2)
    eligibility: list[LocalizedText] = Field(min_length=1)
    pricing: LocalizedText
    """Fictional figures, marked "(fictional)" in the English text."""
    client_view: Text
    """One plain-English line describing the product as a customer would understand it.
    This is what the AI client is told about the product."""

    @field_validator("interest_based")
    @classmethod
    def _not_both_sharia_and_interest(cls, value: bool, info: ValidationInfo) -> bool:
        if value and info.data.get("sharia_compliant") is True:
            raise PydanticCustomError(
                "sharia_and_interest",
                "a product can't be both sharia_compliant and interest_based",
            )
        return value

    @field_validator("pricing")
    @classmethod
    def _figures_marked_fictional(cls, value: LocalizedText) -> LocalizedText:
        if FICTIONAL_MARKER not in value.en:
            raise PydanticCustomError(
                "pricing_not_marked", 'the English text must mark its figures "(fictional)"'
            )
        return value


class Card(_Strict):
    """Public: what students see before the interview."""

    name: LocalizedText
    headline: LocalizedText
    """One line saying who the client is."""
    opening_line: LocalizedText
    """The client's first words when the interview starts."""


class Persona(_Strict):
    """Private: who the AI client plays. English only, because it's an input to the model."""

    age: int
    occupation: Text
    nationality: Text
    family: Text | None = None
    background: Text
    """Keep hidden facts out of this text, or the client may share them before they're earned."""
    personality: Text
    speaking_style: Text
    financial_knowledge: FinancialKnowledge


class HiddenFact(_Strict):
    """Private: something the client shares only once the student has earned it."""

    id: Slug
    content: Text
    """What the client may share once the fact is unlocked."""
    signal: Text | None = None
    """A vague hint the client may drop once while the fact is still locked."""
    unlock_when: list[Text] = Field(min_length=1)
    """Student behaviours that earn the fact, such as "asks how customers pay"."""
    unlock_on_product_pitch: list[Slug] = Field(default_factory=list)
    """Product ids. Proposing any of them makes the client react by revealing this fact."""
    requires: list[Slug] = Field(default_factory=list)
    """Hidden fact ids that must be unlocked before this fact can be."""
    importance: Importance
    example_questions: list[Text] = Field(min_length=1)
    """Questions that should unlock this fact. Used by the evaluations and the coach."""


class UnsuitableProduct(_Strict):
    """A product that doesn't fit a need, and why."""

    id: Slug
    reason: LocalizedText
    """Shown to the student with the feedback. Arabic is optional."""


class Need(_Strict):
    """Private: one part of the answer key."""

    id: Slug
    description: LocalizedText
    """Shown to the student with the feedback. Arabic is optional."""
    evidence_facts: list[Slug] = Field(min_length=1)
    """Hidden fact ids that reveal this need. The student uncovers it by unlocking all of them."""
    suitable_products: list[Slug]
    unsuitable_products: list[UnsuitableProduct]


class CoachNotes(_Strict):
    """Private: guidance for the AI coach."""

    key_questions: list[Text] = Field(min_length=2)
    common_mistakes: list[Text]


class Client(_Strict):
    """One client the student can interview (`content/clients/<id>.yaml`)."""

    id: Slug
    """Lowercase words joined by hyphens. Must equal the file name without `.yaml`."""
    schema_version: Literal[1]
    segment: Segment
    difficulty: Difficulty
    card: Card
    persona: Persona
    open_facts: list[Text] = Field(min_length=1, max_length=6)
    """Things the client shares freely when asked general questions."""
    hidden_facts: list[HiddenFact] = Field(min_length=2, max_length=8)
    needs: list[Need] = Field(min_length=1)
    no_catalogue_fit: bool = False
    """True when no product in the catalogue fits: the right answer is to refer the client."""
    referral_note: LocalizedText | None = Field(default=None, validate_default=True)
    """Where to refer the client. Required when `no_catalogue_fit` is true. Arabic is optional."""
    coach_notes: CoachNotes

    @field_validator("referral_note")
    @classmethod
    def _required_without_a_catalogue_fit(
        cls, value: LocalizedText | None, info: ValidationInfo
    ) -> LocalizedText | None:
        if value is None and info.data.get("no_catalogue_fit") is True:
            raise PydanticCustomError(
                "referral_note_missing", "required when no_catalogue_fit is true"
            )
        return value
