import asyncio
import json
from pathlib import Path

import pytest

from app.telemetry.events import EventLogger


async def test_emit_appends_one_json_line_with_ts_and_event(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "events.jsonl"
    events = EventLogger(path)

    await events.emit("llm_call", role="gate", attempts=1)
    await events.emit("turn", n=2)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["event"] == "llm_call"
    assert first["role"] == "gate"
    assert first["attempts"] == 1
    assert "T" in first["ts"]  # ISO 8601
    assert json.loads(lines[1])["event"] == "turn"


async def test_concurrent_emits_never_interleave(tmp_path: Path) -> None:
    events = EventLogger(tmp_path / "events.jsonl")

    await asyncio.gather(*(events.emit("e", i=i, pad="x" * 2000) for i in range(50)))

    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert sorted(json.loads(line)["i"] for line in lines) == list(range(50))


async def test_write_failure_is_logged_not_raised(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    events = EventLogger(blocker / "events.jsonl")

    await events.emit("llm_call")

    assert "could not write telemetry event" in caplog.text
