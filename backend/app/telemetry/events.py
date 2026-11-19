"""Append-only telemetry: one JSON object per line in `DATA_DIR/events.jsonl`."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)

EVENTS_FILE = "events.jsonl"


class EventLogger:
    """Write telemetry events as JSON lines. Callers must never pass message text."""

    def __init__(self, path: Path) -> None:
        self.path = path
        # One writer at a time, so concurrent events never interleave within a line.
        self._lock = asyncio.Lock()

    async def emit(self, event: str, **fields: object) -> None:
        """Append `{"ts", "event", **fields}` as one line. Failures are logged, never raised."""
        record = {"ts": datetime.now(UTC).isoformat(), "event": event, **fields}
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        try:
            async with self._lock:
                await asyncio.to_thread(self._append, line)
        except OSError as exc:
            # Telemetry must never break the request that produced it.
            logger.warning(
                "could not write telemetry event", extra={"event": event, "error": str(exc)}
            )

    def _append(self, line: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line)


@lru_cache
def event_logger_for(data_dir: Path) -> EventLogger:
    """Return the shared event logger for `data_dir`, so writers to one file share one lock."""
    return EventLogger(data_dir / EVENTS_FILE)


def get_event_logger() -> EventLogger:
    """Return the process-wide event logger, writing under `DATA_DIR`."""
    return event_logger_for(get_settings().DATA_DIR)
