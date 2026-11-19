from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient

from app.api import routes_health
from app.llm import LLMClient, LLMError, ModelTimeout, ModelUnavailable, llm_dep
from app.llm.client import OpenAICompatClient
from app.llm.fake import FakeLLM
from app.main import create_app
from app.telemetry.events import EventLogger
from tests.conftest import TEST_API_KEY, SettingsFactory
from tests.mock_endpoint import MockEndpoint, models

PER_ROLE = {"LLM_MODEL_GATE": "small:4b", "LLM_MODEL": "mid:9b", "LLM_MODEL_COACH": "big:20b"}
HealthClient = Callable[..., TestClient]


@pytest.fixture
def health_client(settings_factory: SettingsFactory, tmp_path: Path) -> HealthClient:
    """A TestClient whose /api/health talks to `llm`, with settings built from overrides."""

    def make(llm: LLMClient, **overrides: Any) -> TestClient:
        settings = settings_factory(FRONTEND_DIST=tmp_path / "missing", **overrides)
        app = create_app(settings)
        app.dependency_overrides[llm_dep] = lambda: llm
        return TestClient(app)

    return make


def test_ok_when_every_role_model_is_available(health_client: HealthClient) -> None:
    llm = FakeLLM(models=["big:20b", "mid:9b", "small:4b", "other:1b"])

    res = health_client(llm, **PER_ROLE).get("/api/health")

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert isinstance(body["version"], str) and body["version"]
    assert body["endpoint"] == {"reachable": True, "host": "llm.test"}
    assert body["models"] == {
        "gate": {"name": "small:4b", "available": True},
        "client": {"name": "mid:9b", "available": True},
        "coach": {"name": "big:20b", "available": True},
    }
    assert body["hint"] is None


def test_degraded_when_a_role_model_is_missing(health_client: HealthClient) -> None:
    llm = FakeLLM(models=["mid:9b", "small:4b"])

    body = health_client(llm, **PER_ROLE).get("/api/health").json()

    assert body["status"] == "degraded"
    assert body["endpoint"]["reachable"] is True
    assert body["models"]["coach"] == {"name": "big:20b", "available": False}
    assert body["models"]["gate"]["available"] is True
    assert body["hint"] == "Model big:20b not found. Run: ollama pull big:20b"


def test_degraded_hint_names_each_missing_model_once(health_client: HealthClient) -> None:
    body = health_client(FakeLLM(models=[]), LLM_MODEL="mid:9b").get("/api/health").json()
    assert body["status"] == "degraded"
    assert body["hint"] == "Model mid:9b not found. Run: ollama pull mid:9b"


def test_untagged_model_names_match_latest(health_client: HealthClient) -> None:
    llm = FakeLLM(models=["llama3.1:latest"])
    body = health_client(llm, LLM_MODEL="llama3.1").get("/api/health").json()
    assert body["status"] == "ok"


@pytest.mark.parametrize(
    "error",
    [ModelUnavailable("refused", reason="unreachable"), ModelTimeout("slow")],
)
def test_down_when_the_endpoint_is_unreachable(
    health_client: HealthClient, error: LLMError
) -> None:
    llm = FakeLLM(list_models_error=error)

    res = health_client(llm, **PER_ROLE).get("/api/health")

    assert res.status_code == 200  # the app itself is up; the body says the models are not
    body = res.json()
    assert body["status"] == "down"
    assert body["endpoint"] == {"reachable": False, "host": "llm.test"}
    assert body["hint"] == "Cannot reach the model endpoint at llm.test. Is Ollama running?"
    assert not any(m["available"] for m in body["models"].values())


def test_down_with_a_key_hint_when_the_endpoint_rejects_the_key(
    health_client: HealthClient,
) -> None:
    llm = FakeLLM(list_models_error=ModelUnavailable("denied", reason="auth"))

    body = health_client(llm).get("/api/health").json()

    assert body["status"] == "down"
    assert body["endpoint"]["reachable"] is True
    assert "LLM_API_KEY" in body["hint"]


def test_shows_only_the_host_never_credentials_path_or_key(
    health_client: HealthClient,
) -> None:
    llm = FakeLLM(models=["test-model"])
    url = "https://user:pa55word@llm.example.com:8443/openai/v1"

    res = health_client(llm, LLM_BASE_URL=url).get("/api/health")

    assert res.json()["endpoint"]["host"] == "llm.example.com:8443"
    for secret in ("pa55word", "user", "/openai/v1", TEST_API_KEY):
        assert secret not in res.text


def test_result_is_cached_for_30_seconds(
    health_client: HealthClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(routes_health, "_now", lambda: clock[0])
    llm = FakeLLM(models=["test-model"])
    client = health_client(llm)

    client.get("/api/health")
    clock[0] += 29
    client.get("/api/health")
    assert llm.list_models_calls == 1

    clock[0] += 2
    client.get("/api/health")
    assert llm.list_models_calls == 2


def test_real_client_reports_down_when_the_connection_is_refused(
    health_client: HealthClient, settings_factory: SettingsFactory, tmp_path: Path
) -> None:
    endpoint = MockEndpoint()
    endpoint.models_reply = httpx2.ConnectError("Connection refused")
    llm = OpenAICompatClient(
        settings_factory(),
        http_client=endpoint.http_client(),
        events=EventLogger(tmp_path / "events.jsonl"),
    )

    body = health_client(llm).get("/api/health").json()

    assert body["status"] == "down"
    assert body["endpoint"]["reachable"] is False
    assert len(endpoint.requests) == 1  # no retries for health


def test_real_client_reports_ok_from_the_models_endpoint(
    health_client: HealthClient, settings_factory: SettingsFactory, tmp_path: Path
) -> None:
    endpoint = MockEndpoint()
    endpoint.models_reply = models("test-model")
    llm = OpenAICompatClient(
        settings_factory(),
        http_client=endpoint.http_client(),
        events=EventLogger(tmp_path / "events.jsonl"),
    )

    assert health_client(llm).get("/api/health").json()["status"] == "ok"
    assert not (tmp_path / "events.jsonl").exists()  # listing models is not an llm_call
