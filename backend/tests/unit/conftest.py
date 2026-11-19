import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.llm.client import OpenAICompatClient
from app.telemetry.events import EventLogger
from tests.conftest import SettingsFactory
from tests.mock_endpoint import MockEndpoint

LLMFactory = Callable[..., OpenAICompatClient]


@pytest.fixture
def endpoint() -> MockEndpoint:
    return MockEndpoint()


@pytest.fixture
def sleeps() -> list[float]:
    """Delays the client asked to sleep for; the fake sleep returns at once."""
    return []


@pytest.fixture
def events_path(tmp_path: Path) -> Path:
    return tmp_path / "events.jsonl"


@pytest.fixture
def make_llm(
    settings_factory: SettingsFactory,
    endpoint: MockEndpoint,
    sleeps: list[float],
    events_path: Path,
) -> LLMFactory:
    """Build an OpenAICompatClient wired to the mock endpoint, with no jitter or real sleeps."""

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    def make(**overrides: Any) -> OpenAICompatClient:
        return OpenAICompatClient(
            settings_factory(**overrides),
            http_client=endpoint.http_client(),
            events=EventLogger(events_path),
            sleep=fake_sleep,
            jitter=lambda: 0.0,
        )

    return make


@pytest.fixture
def read_events(events_path: Path) -> Callable[[], list[dict[str, Any]]]:
    """Read back the telemetry events the client wrote."""

    def read() -> list[dict[str, Any]]:
        if not events_path.exists():
            return []
        lines = events_path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines]

    return read
