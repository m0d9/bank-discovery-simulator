"""Internal interview models. API routes never return these: they map them to DTOs."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Protocol

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SerializeAsAny,
    StringConstraints,
)
from pydantic_core import PydanticCustomError

from app.content import Bank, Client, Product

Language = Literal["en", "ar"]
TurnRole = Literal["student", "client"]

MIN_RECOMMENDATIONS = 1
MAX_RECOMMENDATIONS = 3
NeedsSummary = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=30, max_length=2000)
]
"""The student's summary of the client's needs."""
RecommendationReason = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)
]
"""Why the student recommends a product."""


class SessionStatus(StrEnum):
    """Where a session is in the flow: interview, then wrap-up, then feedback (M5)."""

    INTERVIEWING = "interviewing"
    WRAPPED_UP = "wrapped_up"
    FEEDBACK_READY = "feedback_ready"


class SessionModels(BaseModel):
    """The model each role uses, fixed when the session is created."""

    model_config = ConfigDict(frozen=True)

    gate: str
    client: str
    coach: str


class Turn(BaseModel):
    """One message. `n` counts every message from either side; turn 0 is the opening line."""

    model_config = ConfigDict(frozen=True)

    n: int
    role: TurnRole
    text: str
    ts: datetime
    unlocked: list[str] = Field(default_factory=list)
    """Hidden fact ids this student message unlocked (always empty on client turns)."""
    unlocked_by_pitch: list[str] = Field(default_factory=list)
    """The part of `unlocked` that the product-pitch rule unlocked: the client reacting to a
    product the student proposed, rather than the student asking about the fact."""


class _HasProductId(Protocol):
    @property
    def product_id(self) -> str: ...


def unique_product_ids[T: _HasProductId](recommendations: list[T]) -> list[T]:
    """Reject a wrap-up that recommends the same product twice. Shared with the request DTO."""
    ids = [item.product_id for item in recommendations]
    if len(set(ids)) != len(ids):
        raise PydanticCustomError("duplicate_product", "each product can be recommended only once")
    return recommendations


class Recommendation(BaseModel):
    """One recommended product and the student's reason for it."""

    model_config = ConfigDict(frozen=True)

    product_id: str
    reason: RecommendationReason


class WrapUp(BaseModel):
    """The student's summary and their 1–3 product recommendations."""

    model_config = ConfigDict(frozen=True)

    needs_summary: NeedsSummary
    recommendations: Annotated[
        list[Recommendation],
        Field(min_length=MIN_RECOMMENDATIONS, max_length=MAX_RECOMMENDATIONS),
        AfterValidator(unique_product_ids),
    ]


class Session(BaseModel):
    """One interview, kept in memory by the `SessionStore`.

    It holds the client, bank and catalogue it started with: a content reload changes new
    sessions only, so a running interview's facts never change under it.
    """

    id: str
    client_id: str
    language: Language
    models: SessionModels
    status: SessionStatus = SessionStatus.INTERVIEWING
    turns: list[Turn] = Field(default_factory=list)
    unlocked: dict[str, int] = Field(default_factory=dict)
    """Hidden fact id -> the student turn `n` that unlocked it."""
    products_mentioned: dict[str, list[int]] = Field(default_factory=dict)
    """Product id -> the student turns `n` that proposed or asked about it."""
    wrapup: WrapUp | None = None
    feedback: SerializeAsAny[BaseModel] | None = None
    """The latest feedback (an `app.coaching.Feedback`), set once feedback has been generated.
    Typed loosely so that interviews don't depend on the coaching package."""
    created_at: datetime
    last_active_at: datetime
    client: Client
    bank: Bank
    products: dict[str, Product]
    """The catalogue, by id."""

    @property
    def student_turns_used(self) -> int:
        """How many messages the student has sent."""
        return sum(1 for turn in self.turns if turn.role == "student")
