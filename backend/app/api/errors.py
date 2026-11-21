"""The API's error envelope, and how typed errors map to it.

Every error response is `{"error": {"code", "message_key", "detail"}}`, where `message_key` is
`errors.<code>` for the UI to translate. `STATUS_BY_CODE` is the one table of codes and HTTP
statuses: the handlers below use it, and `make openapi` writes its codes to
`frontend/src/api/error-codes.json`.
"""

import logging
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.dto import ErrorEnvelopeDTO
from app.api.routes_health import forget_cached_health
from app.content import UnknownClient, UnknownProduct
from app.llm import LLMError
from app.simulation import InterviewError

logger = logging.getLogger(__name__)

STATUS_BY_CODE: dict[str, int] = {
    "NOT_FOUND": 404,
    "SESSION_NOT_FOUND": 404,
    "UNKNOWN_CLIENT": 404,
    "SESSION_BUSY": 409,
    "TURN_LIMIT": 409,
    "INVALID_STATE": 409,
    "REQUEST_TOO_LARGE": 413,
    "INVALID_INPUT": 422,
    "RATE_LIMITED": 429,
    "INTERNAL_ERROR": 500,
    "INVALID_OUTPUT": 502,
    "LLM_ERROR": 502,
    "MODEL_UNAVAILABLE": 503,
    "MODEL_TIMEOUT": 504,
}
ERROR_CODES: tuple[str, ...] = tuple(STATUS_BY_CODE)

_ENDPOINT_FAILURES = frozenset({"MODEL_UNAVAILABLE", "MODEL_TIMEOUT"})
_ID_LIMIT = 100
_DETAIL_LIMIT = 500
_REQUEST_PARTS = ("body", "path", "query")


def error_body(code: str, detail: str | None = None) -> dict[str, Any]:
    """The envelope for `code`."""
    return {"error": {"code": code, "message_key": f"errors.{code}", "detail": detail}}


def error_response(code: str, detail: str | None = None) -> JSONResponse:
    """The envelope for `code`, with the code's HTTP status."""
    return JSONResponse(status_code=STATUS_BY_CODE[code], content=error_body(code, detail))


def error_responses(*codes: str) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` for a route that can fail with `codes`, grouped by status.

    Listing 422 here also replaces FastAPI's default validation-error schema, which this API
    never sends.
    """
    by_status: dict[int, list[str]] = {}
    for code in codes:
        by_status.setdefault(STATUS_BY_CODE[code], []).append(code)
    return {
        status: {"model": ErrorEnvelopeDTO, "description": ", ".join(grouped)}
        for status, grouped in sorted(by_status.items())
    }


def register_error_handlers(app: FastAPI) -> None:
    """Turn every typed error, invalid request and unexpected exception into the envelope."""
    app.add_exception_handler(InterviewError, _interview_error)
    app.add_exception_handler(UnknownClient, _unknown_client)
    app.add_exception_handler(UnknownProduct, _unknown_product)
    app.add_exception_handler(LLMError, _model_error)
    app.add_exception_handler(RequestValidationError, _invalid_request)
    app.add_exception_handler(Exception, _unexpected)


async def _interview_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, InterviewError):
        raise exc
    return error_response(exc.code, exc.detail or None)


async def _unknown_client(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, UnknownClient):
        raise exc
    return error_response("UNKNOWN_CLIENT", f"no client has the id '{exc.client_id[:_ID_LIMIT]}'")


async def _unknown_product(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, UnknownProduct):
        raise exc
    return error_response("INVALID_INPUT", f"unknown product '{exc.product_id[:_ID_LIMIT]}'")


async def _model_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, LLMError):
        raise exc
    if exc.code in _ENDPOINT_FAILURES:
        # A cached "ok" may be stale now, and the UI checks /api/health after these errors.
        forget_cached_health(request.app)
    # `detail` is one of the model layer's fixed strings, never the server's own message.
    return error_response(exc.code, exc.detail or None)


async def _invalid_request(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    return error_response("INVALID_INPUT", _validation_detail(exc.errors()))


async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
    # The exception's own message could quote anything, so the response says nothing about
    # it. Starlette re-raises the exception after this response, so the server logs it.
    logger.error(
        "Unexpected error",
        extra={"method": request.method, "path": request.url.path, "error": type(exc).__name__},
    )
    return error_response("INTERNAL_ERROR")


def _validation_detail(errors: Sequence[Any]) -> str:
    """`field: problem` for each error, naming fields and never repeating the input."""
    problems = []
    for error in errors:
        loc = list(error.get("loc", ()))
        if len(loc) > 1 and loc[0] in _REQUEST_PARTS:
            loc = loc[1:]
        problems.append(f"{_location(loc)}: {error.get('msg', 'invalid value')}")
    return "; ".join(problems)[:_DETAIL_LIMIT]


def _location(loc: Sequence[Any]) -> str:
    text = ""
    for part in loc:
        text += f"[{part}]" if isinstance(part, int) else (f".{part}" if text else str(part))
    return text or "request"
