"""Data transfer objects: the only shapes API routes may return."""

from typing import Literal

from pydantic import BaseModel


class HealthOut(BaseModel):
    """Response of `GET /api/health`."""

    status: Literal["ok"]
    version: str
