"""Typed errors for model calls. `code` is also the API error code (`errors.<CODE>`)."""

from typing import ClassVar, Literal

# Why a model can't be used; lets /api/health pick the right hint.
UnavailableReason = Literal["unreachable", "not_found", "auth", "server_error"]

_RAW_TEXT_LIMIT = 500


class LLMError(Exception):
    """Base class for every model-call failure. `detail` never contains message text."""

    code: ClassVar[str] = "LLM_ERROR"

    def __init__(self, detail: str = "") -> None:
        super().__init__(detail or self.code)
        self.detail = detail


class ModelUnavailable(LLMError):
    """The endpoint is unreachable, rejects the key, lacks the model, or keeps failing (5xx)."""

    code = "MODEL_UNAVAILABLE"

    def __init__(self, detail: str = "", *, reason: UnavailableReason = "unreachable") -> None:
        super().__init__(detail)
        self.reason: UnavailableReason = reason


class ModelTimeout(LLMError):
    """The model did not answer within the role's timeout, even after retries."""

    code = "MODEL_TIMEOUT"


class RateLimited(LLMError):
    """The endpoint kept answering 429 after retries."""

    code = "RATE_LIMITED"


class InvalidOutput(LLMError):
    """The reply was unusable: JSON still invalid after the retry, or no text at all.

    `raw_text` keeps at most 500 characters of the reply for debugging. Never log it.
    """

    code = "INVALID_OUTPUT"

    def __init__(self, detail: str = "", *, raw_text: str = "") -> None:
        super().__init__(detail)
        self.raw_text = raw_text[:_RAW_TEXT_LIMIT]


class OutputTruncated(InvalidOutput):
    """The model hit max_tokens before producing usable output (often on hidden reasoning)."""


def outcome_of(error: LLMError) -> str:
    """Return the `outcome` value that `llm_call` events record for `error`."""
    return "truncated" if isinstance(error, OutputTruncated) else error.code
