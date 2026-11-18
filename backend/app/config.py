"""Application settings, read from the environment (and `.env`)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration. Every field has a default so the app starts with no `.env`."""

    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    APP_ENV: Literal["dev", "test", "prod"] = "dev"
    FRONTEND_DIST: Path = _REPO_ROOT / "frontend" / "dist"
    CONTENT_DIR: Path = _REPO_ROOT / "content"
    DATA_DIR: Path = _REPO_ROOT / "data"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance (cached)."""
    return Settings()
