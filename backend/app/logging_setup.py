"""Stdlib logging configured to emit one JSON object per line, with secrets redacted."""

import json
import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

# Attributes every LogRecord has; anything else was passed via `extra=` and is emitted.
_RESERVED = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}
_PLAIN = (int, float, bool, type(None))
_EXCEPTION_FORMATTER = logging.Formatter()

REDACTED = "[REDACTED]"

# HTTP client libraries log every request at INFO. That's noise in the app's log and in the
# middle of scripts/chat.py's conversation; their warnings and errors still come through.
QUIET_LOGGERS = ("httpx", "httpx2", "openai")


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        elif record.exc_text:
            payload["exc"] = record.exc_text
        return json.dumps(payload, default=str, ensure_ascii=False)


class RedactSecretsFilter(logging.Filter):
    """Replace secret values (such as the API key) wherever they appear in a log record.

    Covers the rendered message, `extra=` fields, exception text and stack info. Install it on
    a handler so records propagated from every logger pass through it.
    """

    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self._secrets = tuple(secret for secret in secrets if secret)

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._secrets:
            return True
        try:
            message = record.getMessage()
        except Exception:  # malformed %-args: keep the raw template rather than crash logging
            message = str(record.msg)
        record.msg, record.args = self._redact(message), None
        for key, value in list(vars(record).items()):
            if key in _RESERVED or key.startswith("_") or isinstance(value, _PLAIN):
                continue
            text = value if isinstance(value, str) else repr(value)
            if any(secret in text for secret in self._secrets):
                setattr(record, key, self._redact(text))
        if record.exc_info:
            record.exc_text = self._redact(_EXCEPTION_FORMATTER.formatException(record.exc_info))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = self._redact(record.exc_text)
        if record.stack_info:
            record.stack_info = self._redact(record.stack_info)
        return True

    def _redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return text


def configure_logging(level: int | str = logging.INFO, *, secrets: Iterable[str] = ()) -> None:
    """Install the JSON formatter and the secret-redacting filter on the root logger, and keep
    the HTTP client libraries at WARNING.

    Idempotent: replaces any handlers already on the root logger.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactSecretsFilter(secrets))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
