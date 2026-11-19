"""Data transfer objects: the only shapes API routes may return."""

from typing import Literal

from pydantic import BaseModel

HealthStatus = Literal["ok", "degraded", "down"]


class EndpointOut(BaseModel):
    """The model endpoint: its host only (never the URL or key), and whether it answered."""

    reachable: bool
    host: str


class ModelStatusOut(BaseModel):
    """One role's model and whether the endpoint offers it."""

    name: str
    available: bool


class ModelsOut(BaseModel):
    """The model each role uses."""

    gate: ModelStatusOut
    client: ModelStatusOut
    coach: ModelStatusOut


class HealthOut(BaseModel):
    """Response of `GET /api/health`.

    `down`: the endpoint can't be used. `degraded`: a role's model is missing. `hint` says
    what to do about either.
    """

    status: HealthStatus
    version: str
    endpoint: EndpointOut
    models: ModelsOut
    hint: str | None
