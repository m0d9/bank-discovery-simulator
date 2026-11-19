"""Model access: every model call in the app goes through this package.

Import from here, not from submodules (`app/api` is held to that by an architecture test).
Tests swap the client by overriding `llm_dep`, or use `app.llm.fake.FakeLLM` directly.
"""

from functools import lru_cache

from app.config import get_settings
from app.llm.client import LLMClient, OpenAICompatClient, endpoint_host
from app.llm.errors import (
    InvalidOutput,
    LLMError,
    ModelTimeout,
    ModelUnavailable,
    OutputTruncated,
    RateLimited,
)
from app.llm.roles import Role, resolve_model
from app.llm.types import ChatMessage, LLMResult

__all__ = [
    "ChatMessage",
    "InvalidOutput",
    "LLMClient",
    "LLMError",
    "LLMResult",
    "ModelTimeout",
    "ModelUnavailable",
    "OutputTruncated",
    "RateLimited",
    "Role",
    "endpoint_host",
    "get_llm",
    "llm_dep",
    "resolve_model",
]


@lru_cache
def get_llm() -> LLMClient:
    """Return the process-wide model client, configured from settings."""
    return OpenAICompatClient(get_settings())


def llm_dep() -> LLMClient:
    """FastAPI dependency that provides the model client. Tests override it."""
    return get_llm()
