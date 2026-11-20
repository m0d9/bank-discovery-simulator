"""Data transfer objects: the only shapes API routes may return."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

from app.coaching import DiscoveredBy, NeedStatus, Verdict
from app.content import Category, Difficulty, FinancialKnowledge, Importance, Segment
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


class SubmittedWrapUpDTO(BaseModel):
    """The wrap-up as the student submitted it."""

    needs_summary: str
    recommendations: list[RecommendationDTO]


class FactUnlockDTO(BaseModel):
    """One evidence fact of a need, and the student turn that unlocked it (null if it never
    came out)."""

    fact_id: str
    unlocked_at_turn: int | None


class NeedViaDTO(BaseModel):
    """The student turn whose answer completed a need, and what the student said in it."""

    turn: int
    question: str


class NeedResultDTO(BaseModel):
    """`uncovered` when the student's questions brought out every evidence fact;
    `revealed_by_pitch` when every fact came out, but at least one only in reaction to a product
    the student pitched; `partial` when some did; `missed` when none did. `via` is set when every
    fact came out."""

    need_id: str
    status: NeedStatus
    facts: list[FactUnlockDTO]
    via: NeedViaDTO | None


class FactResultDTO(BaseModel):
    """When a hidden fact came out, and whether a question or a product pitch brought it out."""

    fact_id: str
    importance: Importance
    unlocked_at_turn: int | None
    discovered_by: DiscoveredBy | None


class VerdictReasonDTO(BaseModel):
    """Why a product is unsuitable: for one need, or (`need_id` null) the referral note."""

    need_id: str | None
    reason: LocalizedTextDTO


class ProductVerdictDTO(BaseModel):
    """A recommended product against the answer key: `reasons` when it's unsuitable, `needs`
    (the needs it meets) when it's suitable."""

    product_id: str
    verdict: Verdict
    reasons: list[VerdictReasonDTO]
    needs: list[str]


class MissedOpportunityDTO(BaseModel):
    """A suitable product the student didn't recommend, and the needs it would have met."""

    product_id: str
    needs: list[str]


class FeedbackStatsDTO(BaseModel):
    """Counts, never scores."""

    student_turns: int
    needs_uncovered: int
    """Needs the student's questions found (`uncovered` only)."""
    needs_after_pitch: int
    """Needs found in full, but only after a pitch (`revealed_by_pitch`)."""
    needs_total: int
    critical_found: int
    critical_total: int
    first_unlock_turn: int | None


class AnalysisDTO(BaseModel):
    """What code works out about the interview, without a model. Always accurate."""

    needs: list[NeedResultDTO]
    facts: list[FactResultDTO]
    products: list[ProductVerdictDTO]
    missed_opportunities: list[MissedOpportunityDTO]
    stats: FeedbackStatsDTO


class WentWellDTO(BaseModel):
    """Something the student did well, and the student turns that show it."""

    point: str
    evidence_turns: list[int]


class MissedPointDTO(BaseModel):
    """Something the student missed, with a question they could have asked."""

    point: str
    need_id: str | None
    product_id: str | None
    evidence_turns: list[int]
    better_question: str | None


class ImprovementDTO(BaseModel):
    """A habit for the next interview, with an example."""

    tip: str
    example: str | None


class CoachReportDTO(BaseModel):
    """The AI coach's report, in the feedback's language."""

    went_well: list[WentWellDTO]
    missed: list[MissedPointDTO]
    how_to_improve: list[ImprovementDTO]
    summary_feedback: str


class PersonaDTO(BaseModel):
    """Who the AI client played. The content keeps these fields in English."""

    age: int
    occupation: LocalizedTextDTO
    nationality: LocalizedTextDTO
    family: LocalizedTextDTO | None
    background: LocalizedTextDTO
    personality: LocalizedTextDTO
    speaking_style: LocalizedTextDTO
    financial_knowledge: FinancialKnowledge


class RevealedFactDTO(BaseModel):
    """A hidden fact, revealed, and the student turn that unlocked it (null if it never did)."""

    id: str
    content: LocalizedTextDTO
    importance: Importance
    unlocked_at_turn: int | None


class UnsuitableProductDTO(BaseModel):
    """A product that doesn't meet a need, and why."""

    id: str
    reason: LocalizedTextDTO


class RevealedNeedDTO(BaseModel):
    """One part of the answer key, with how far the student uncovered it."""

    id: str
    description: LocalizedTextDTO
    status: NeedStatus
    suitable_products: list[str]
    unsuitable_products: list[UnsuitableProductDTO]


class RevealedClientDTO(BaseModel):
    """The client's private profile, shown once the interview has its feedback."""

    persona: PersonaDTO
    open_facts: list[LocalizedTextDTO]
    hidden_facts: list[RevealedFactDTO]
    needs: list[RevealedNeedDTO]
    no_catalogue_fit: bool
    referral_note: LocalizedTextDTO | None


class FeedbackDTO(BaseModel):
    """Response of `POST /api/sessions/{session_id}/feedback`.

    `analysis` is always present and accurate. `report` is the coach's, in `language`; it is
    null, with `degraded` true, when the coach was unavailable. The only response that carries
    the client's private profile (`revealed`).
    """

    session_id: str
    language: Language
    analysis: AnalysisDTO
    report: CoachReportDTO | None
    degraded: bool
    models: SessionModelsDTO
    generated_at: datetime
    wrapup: SubmittedWrapUpDTO
    revealed: RevealedClientDTO


class ErrorDTO(BaseModel):
    """What went wrong. `message_key` is `errors.<code>`, for the UI to translate; `detail` is
    English for developers, and never contains message text."""

    code: str
    message_key: str
    detail: str | None


class ErrorEnvelopeDTO(BaseModel):
    """Every error response: `{"error": {"code", "message_key", "detail"}}`."""

    error: ErrorDTO
