import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from app.llm.errors import ModelUnavailable
from app.llm.roles import Role
from app.llm.types import ChatMessage
from app.logging_setup import REDACTED, JsonFormatter, RedactSecretsFilter, configure_logging
from tests.conftest import TEST_API_KEY
from tests.mock_endpoint import MockEndpoint, completion, error
from tests.unit.conftest import LLMFactory

SECRET = "s3cret-key-value"


def test_json_formatter_emits_json_with_extras() -> None:
    record = logging.makeLogRecord(
        {"name": "t", "levelname": "INFO", "msg": "hello %s", "args": ("x",), "session": "s1"}
    )
    out = json.loads(JsonFormatter().format(record))
    assert out["msg"] == "hello x"
    assert out["level"] == "INFO"
    assert out["session"] == "s1"


def _filtered(**fields: Any) -> logging.LogRecord:
    record = logging.makeLogRecord({"name": "t", "levelname": "INFO", **fields})
    assert RedactSecretsFilter([SECRET]).filter(record) is True
    return record


def test_redacts_the_rendered_message_and_string_extras() -> None:
    record = _filtered(msg="key=%s", args=(SECRET,), header=f"Bearer {SECRET}", count=3)
    out = json.loads(JsonFormatter().format(record))
    assert out["msg"] == f"key={REDACTED}"
    assert out["header"] == f"Bearer {REDACTED}"
    assert out["count"] == 3


def test_redacts_structured_extras() -> None:
    record = _filtered(msg="m", options={"headers": {"Authorization": f"Bearer {SECRET}"}})
    assert SECRET not in JsonFormatter().format(record)


def test_redacts_exception_text() -> None:
    try:
        raise RuntimeError(f"auth failed for {SECRET}")
    except RuntimeError:
        record = _filtered(msg="boom", exc_info=sys.exc_info())
    out = JsonFormatter().format(record)
    assert SECRET not in out
    assert "RuntimeError" in out
    assert REDACTED in out


def test_malformed_args_do_not_break_logging() -> None:
    record = _filtered(msg="%d items", args=("not a number",))
    assert json.loads(JsonFormatter().format(record))["msg"] == "%d items"


def test_without_secrets_records_are_untouched() -> None:
    record = logging.makeLogRecord({"msg": "hello %s", "args": ("x",)})
    assert RedactSecretsFilter(["", ""]).filter(record) is True
    assert record.args == ("x",)


@contextmanager
def json_logs_to_stderr(level: int, secrets: list[str]) -> Iterator[None]:
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    configure_logging(level, secrets=secrets)
    try:
        yield
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


async def test_api_key_never_reaches_the_log_output(
    make_llm: LLMFactory, endpoint: MockEndpoint, capsys: pytest.CaptureFixture[str]
) -> None:
    messages = [ChatMessage(role="user", content="hello")]
    endpoint.queue(completion("hi"), error(401, f"Incorrect API key provided: {TEST_API_KEY}"))
    log = logging.getLogger("app.test")

    # DEBUG on purpose: the SDK and the HTTP stack log request details at that level.
    with json_logs_to_stderr(logging.DEBUG, [TEST_API_KEY]):
        llm = make_llm()
        await llm.chat(Role.CLIENT, messages, max_tokens=5, temperature=0)
        with pytest.raises(ModelUnavailable):
            await llm.chat(Role.CLIENT, messages, max_tokens=5, temperature=0)
        log.warning("configured key %s", TEST_API_KEY, extra={"auth": f"Bearer {TEST_API_KEY}"})
        try:
            raise RuntimeError(f"request failed with {TEST_API_KEY}")
        except RuntimeError:
            log.exception("request failed")

    output = capsys.readouterr().err
    assert REDACTED in output  # the key was there to redact
    assert TEST_API_KEY not in output
