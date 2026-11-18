import json
import logging

from app.logging_setup import JsonFormatter


def test_json_formatter_emits_json_with_extras() -> None:
    record = logging.makeLogRecord(
        {"name": "t", "levelname": "INFO", "msg": "hello %s", "args": ("x",), "session": "s1"}
    )
    out = json.loads(JsonFormatter().format(record))
    assert out["msg"] == "hello x"
    assert out["level"] == "INFO"
    assert out["session"] == "s1"
