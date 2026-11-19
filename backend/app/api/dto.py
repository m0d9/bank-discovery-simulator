"""Data transfer objects: the only shapes API routes may return."""

from typing import Literal

from pydantic import BaseModel

from app.content import Category, Difficulty, Segment

HealthStatus = Literal["ok", "degraded", "down"]


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
    what to do about either. `content` reports the content files separately.
    """

    status: HealthStatus
    version: str
    endpoint: EndpointDTO
    models: ModelsDTO
    hint: str | None
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
