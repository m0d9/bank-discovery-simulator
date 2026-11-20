"""Data transfer objects: the only shapes API routes may return."""

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

from app.content import Category, Difficulty, Segment
from app.simulation.models import (
    MAX_RECOMMENDATIONS,
    MIN_RECOMMENDATIONS,
    Language,
    NeedsSummary,
    RecommendationReason,
    SessionStatus,
    TurnRole,
    unique_product_ids,
)

HealthStatus = Literal["ok", "degraded", "down"]
HealthHintCode = Literal["ENDPOINT_UNREACHABLE", "ENDPOINT_AUTH", "ENDPOINT_ERROR", "MODEL_MISSING"]


class EndpointDTO(BaseModel):
    """The model endpoint: its host only (never the URL or key), and whether it answered."""

    reachable: bool
    host: str


class ModelStatusDTO(BaseModel):
    """One role's model and whether the endpoint offers it."""

    name: str
    available: bool


class ModelsDTO(BaseModel):
    """The model each role uses."""

    gate: ModelStatusDTO
    client: ModelStatusDTO
    coach: ModelStatusDTO


class ContentStatusDTO(BaseModel):
    """Whether the content files are valid. While they aren't, the last good version is served
    and `errors` lists each problem with its file and field."""

    ok: bool
    errors: list[str]


class HealthDTO(BaseModel):
    """Response of `GET /api/health`.

    `down`: the endpoint can't be used. `degraded`: a role's model is missing. `hint` says
    what to do about either, in English for whoever runs the app; `hint_code` names the same
    problem for the UI to translate (`health.<CODE>`). `content` reports the content files
    separately.
    """

    status: HealthStatus
    version: str
    endpoint: EndpointDTO
    models: ModelsDTO
    hint: str | None
    hint_code: HealthHintCode | None
    content: ContentStatusDTO


class LocalizedTextDTO(BaseModel):
    """Text in English, and in Arabic when the content provides it (`null` otherwise)."""

    en: str
    ar: str | None


class BankDTO(BaseModel):
    """Response of `GET /api/bank`: the fictional bank."""

    name: LocalizedTextDTO
    tagline: LocalizedTextDTO
    disclaimer: LocalizedTextDTO
    currency: Literal["QAR"]


class ClientCardDTO(BaseModel):
    """A client's public card: all a student sees before starting the interview."""

    id: str
    segment: Segment
    difficulty: Difficulty
    name: LocalizedTextDTO
    headline: LocalizedTextDTO


class ProductDTO(BaseModel):
    """A product as students see it in the catalogue."""

    id: str
    name: LocalizedTextDTO
    summary: LocalizedTextDTO
    segments: list[Segment]
    category: Category
    sharia_compliant: bool
    interest_based: bool
    features: list[LocalizedTextDTO]
    limitations: list[LocalizedTextDTO]
    eligibility: list[LocalizedTextDTO]
    pricing: LocalizedTextDTO


class SessionModelsDTO(BaseModel):
    """The model each role uses in a session, fixed when the session is created."""

    gate: str
    client: str
    coach: str


class TurnDTO(BaseModel):
    """One message in the transcript. It never says which facts a message unlocked."""

    n: int
    role: TurnRole
    text: str


class CreateSessionDTO(BaseModel):
    """Request body of `POST /api/sessions`."""

    client_id: str
    language: Language
    """The language of the opening line and of the fallback line."""


class SessionCreatedDTO(BaseModel):
    """Response of `POST /api/sessions`."""

    session_id: str
    client: ClientCardDTO
    opening_line: LocalizedTextDTO
    max_student_turns: int
    max_message_chars: int
    models: SessionModelsDTO


class SessionPublicDTO(BaseModel):
    """A session as the student may see it: the card, the transcript and the counters."""

    session_id: str
    client: ClientCardDTO
    status: SessionStatus
    language: Language
    turns: list[TurnDTO]
    student_turns_used: int
    max_student_turns: int
    max_message_chars: int
    models: SessionModelsDTO


class StudentMessageDTO(BaseModel):
    """Request body of `POST /api/sessions/{session_id}/messages`.

    The length limit (`max_message_chars`) is checked after control characters are removed.
    """

    text: str


class MessageResultDTO(BaseModel):
    """Response of `POST /api/sessions/{session_id}/messages`: the exchange and the counters."""

    student_turn: TurnDTO
    client_turn: TurnDTO
    student_turns_used: int
    max_student_turns: int


class RecommendationDTO(BaseModel):
    """One recommended product and why."""

    product_id: str
    reason: RecommendationReason


class WrapUpDTO(BaseModel):
    """Request body of `POST /api/sessions/{session_id}/wrapup`."""

    needs_summary: NeedsSummary
    recommendations: Annotated[
        list[RecommendationDTO],
        Field(min_length=MIN_RECOMMENDATIONS, max_length=MAX_RECOMMENDATIONS),
        AfterValidator(unique_product_ids),
    ]


class ErrorDTO(BaseModel):
    """What went wrong. `message_key` is `errors.<code>`, for the UI to translate; `detail` is
    English for developers, and never contains message text."""

    code: str
    message_key: str
    detail: str | None


class ErrorEnvelopeDTO(BaseModel):
    """Every error response: `{"error": {"code", "message_key", "detail"}}`."""

    error: ErrorDTO
