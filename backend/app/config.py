"""Application settings, read from the environment (and `.env`)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration.

    Only `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` are required; everything else has a
    default. Empty values (`NAME=`) count as unset, so commented-out examples stay harmless.
    """

    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    APP_ENV: Literal["dev", "test", "prod"] = "dev"
    FRONTEND_DIST: Path = _REPO_ROOT / "frontend" / "dist"
    CONTENT_DIR: Path = _REPO_ROOT / "content"
    DATA_DIR: Path = _REPO_ROOT / "data"

    # Model endpoint: any OpenAI-compatible Chat Completions API (required).
    LLM_BASE_URL: str = Field(pattern=r"^https?://\S+$")
    LLM_API_KEY: SecretStr = Field(min_length=1)
    LLM_MODEL: str = Field(min_length=1)

    # Per-role models; each falls back to LLM_MODEL.
    LLM_MODEL_GATE: str | None = None
    LLM_MODEL_CLIENT: str | None = None
    LLM_MODEL_COACH: str | None = None

    # The coach waits longest: Ollama may have to swap models into memory first.
    LLM_TIMEOUT_GATE_S: float = Field(default=30, gt=0)
    LLM_TIMEOUT_CLIENT_S: float = Field(default=90, gt=0)
    LLM_TIMEOUT_COACH_S: float = Field(default=240, gt=0)

    LLM_MAX_CONCURRENCY: int = Field(default=1, ge=1)
    LLM_MAX_RETRIES: int = Field(default=2, ge=0)
    LLM_DISABLE_THINKING: bool = True

    # USD per million tokens; used only for cost estimates in telemetry.
    LLM_PRICE_INPUT_PER_MTOK: float | None = Field(default=None, ge=0)
    LLM_PRICE_OUTPUT_PER_MTOK: float | None = Field(default=None, ge=0)

    ALLOW_MODEL_SWITCH: bool = False
    LOG_TRANSCRIPTS: bool = False

    # Interview sessions live in memory only; a restart clears them.
    SESSION_TTL_MINUTES: int = Field(default=120, ge=1)
    MAX_SESSIONS: int = Field(default=200, ge=1)
    MAX_STUDENT_TURNS: int = Field(default=30, ge=1)
    MAX_MESSAGE_CHARS: int = Field(default=1000, ge=1)
    CLIENT_HISTORY_TURNS: int = Field(default=12, ge=1)
    MAX_UNLOCKS_PER_TURN: int = Field(default=2, ge=1)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance (cached)."""
    return Settings()
