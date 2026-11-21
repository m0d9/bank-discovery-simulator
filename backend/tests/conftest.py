"""Shared fixtures. Non-live tests never read the developer's `.env` or call a real model."""

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings

# `app.main` builds its default app at import time, and that needs the three required LLM_*
# settings. CI has no `.env`, so placeholders are supplied only when they're missing; a real
# `.env` (or exported variables) stays in effect for `-m live` runs.
try:
    Settings()
except ValidationError:
    for _name, _value in {
        "LLM_BASE_URL": "http://llm.invalid/v1",
        "LLM_API_KEY": "placeholder",
        "LLM_MODEL": "placeholder",
    }.items():
        os.environ.setdefault(_name, _value)

from app.llm import llm_dep  # noqa: E402
from app.llm.fake import FakeLLM  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.content_factory import ContentDir, make_content  # noqa: E402

TEST_BASE_URL = "http://llm.test/v1"
# Deliberately low-entropy so secret scanners don't flag the test suite.
TEST_API_KEY = "test-key-not-a-secret"
TEST_MODEL = "test-model"

SettingsFactory = Callable[..., Settings]


@pytest.fixture(autouse=True)
def _hermetic_env(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hide exported settings from non-live tests so a developer's shell can't change results."""
    if request.node.get_closest_marker("live"):
        return
    for name in Settings.model_fields:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings_factory(tmp_path: Path) -> SettingsFactory:
    """Build settings from explicit test values only (no `.env`), with optional overrides."""

    def make(**overrides: Any) -> Settings:
        values: dict[str, Any] = {
            "APP_ENV": "test",
            "DATA_DIR": tmp_path / "data",
            "LLM_BASE_URL": TEST_BASE_URL,
            "LLM_API_KEY": TEST_API_KEY,
            "LLM_MODEL": TEST_MODEL,
            # Fake replies are instant, so API tests would trip the 1 s message interval;
            # tests/api/test_security.py checks it with a moved clock.
            "MIN_MESSAGE_INTERVAL_S": 0,
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)

    return make


@pytest.fixture
def settings(settings_factory: SettingsFactory) -> Settings:
    return settings_factory()


@pytest.fixture
def content(tmp_path: Path) -> ContentDir:
    """Valid sample content in `tmp_path/content`, for tests to change or break."""
    return make_content(tmp_path)


@pytest.fixture
def dist_dir(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>spa</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('x')", encoding="utf-8")
    return dist


@pytest.fixture
def fake_llm() -> FakeLLM:
    """A FakeLLM whose endpoint offers the test model, so /api/health reports ok."""
    return FakeLLM(models=[TEST_MODEL])


@pytest.fixture
def client(
    dist_dir: Path, settings_factory: SettingsFactory, fake_llm: FakeLLM
) -> Iterator[TestClient]:
    app = create_app(settings_factory(FRONTEND_DIST=dist_dir))
    app.dependency_overrides[llm_dep] = lambda: fake_llm
    with TestClient(app) as c:
        yield c


@pytest.fixture
def dev_client(
    tmp_path: Path, settings_factory: SettingsFactory, fake_llm: FakeLLM
) -> Iterator[TestClient]:
    app = create_app(settings_factory(FRONTEND_DIST=tmp_path / "missing"))
    app.dependency_overrides[llm_dep] = lambda: fake_llm
    with TestClient(app) as c:
        yield c
