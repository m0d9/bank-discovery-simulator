"""Security hygiene: response headers and the CSP, the request body limit, and the
per-session message interval."""

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import throttle
from app.api.throttle import MessageThrottle
from app.llm import Role, llm_dep
from app.llm.fake import FakeLLM
from app.main import create_app
from tests.conftest import SettingsFactory
from tests.interview_factory import gate_reply

CSP = (
    "default-src 'self'; img-src 'self' data:; font-src 'self'; style-src 'self'; "
    "frame-ancestors 'none'"
)
MAX_BODY = 32 * 1024
JSON = {"content-type": "application/json"}
OTHER_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        ("GET", "/", 200),  # the SPA's index.html
        ("GET", "/interview/x", 200),  # a client route, served the same index.html
        ("GET", "/assets/app.js", 200),
        ("GET", "/api/health", 200),
        ("GET", "/api/nope", 404),  # an error envelope
        ("POST", "/api/sessions", 422),
    ],
)
def test_every_response_has_the_csp_and_the_security_headers(
    client: TestClient, method: str, path: str, status: int
) -> None:
    res = client.request(method, path)

    assert res.status_code == status
    assert res.headers["content-security-policy"] == CSP
    for name, value in OTHER_HEADERS.items():
        assert res.headers[name] == value, name


def test_the_api_docs_page_only_forbids_framing(client: TestClient) -> None:
    # Swagger UI needs its CDN and an inline script; the page has no user content.
    res = client.get("/api/docs")

    assert res.status_code == 200
    assert res.headers["content-security-policy"] == "frame-ancestors 'none'"
    assert res.headers["x-content-type-options"] == "nosniff"


def test_a_body_over_32_kb_gets_413_in_the_error_envelope(client: TestClient) -> None:
    res = client.post("/api/sessions", content=b"x" * (MAX_BODY + 1), headers=JSON)

    assert res.status_code == 413
    assert res.json() == {
        "error": {
            "code": "REQUEST_TOO_LARGE",
            "message_key": "errors.REQUEST_TOO_LARGE",
            "detail": f"the request body is larger than {MAX_BODY} bytes",
        }
    }
    assert res.headers["content-security-policy"] == CSP


def test_a_chunked_body_over_32_kb_is_refused_too(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(33):
            yield b"x" * 1024

    res = client.post("/api/sessions", content=chunks(), headers=JSON)

    assert "content-length" not in res.request.headers  # no declared length to go by
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "REQUEST_TOO_LARGE"


def test_a_body_of_exactly_32_kb_reaches_the_app(client: TestClient) -> None:
    empty = json.dumps({"client_id": "", "language": "en"})
    body = json.dumps({"client_id": "x" * (MAX_BODY - len(empty)), "language": "en"})
    assert len(body.encode()) == MAX_BODY

    res = client.post("/api/sessions", content=body, headers=JSON)

    assert res.status_code == 404
    assert res.json()["error"]["code"] == "UNKNOWN_CLIENT"


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """The throttle's clock, in seconds; tests move it by hand."""
    now = [1000.0]
    monkeypatch.setattr(throttle, "_now", lambda: now[0])
    return now


@pytest.fixture
def throttled(
    settings_factory: SettingsFactory, fake_llm: FakeLLM, tmp_path: Path, clock: list[float]
) -> Iterator[TestClient]:
    """The API with the default 1 s message interval (the test settings turn it off)."""
    settings = settings_factory(FRONTEND_DIST=tmp_path / "missing", MIN_MESSAGE_INTERVAL_S=1.0)
    app = create_app(settings)
    app.dependency_overrides[llm_dep] = lambda: fake_llm
    with TestClient(app) as test_client:
        yield test_client


def _start(api: TestClient) -> str:
    created = api.post("/api/sessions", json={"client_id": "noura-al-kuwari", "language": "en"})
    assert created.status_code == 201, created.text
    session_id: str = created.json()["session_id"]
    return session_id


def _send(api: TestClient, session_id: str, fake: FakeLLM | None = None) -> httpx.Response:
    """Send a message; script the gate and the client when it should get through."""
    if fake is not None:
        fake.script(Role.GATE, gate_reply())
        fake.script(Role.CLIENT, "Some of them pay late.")
    return api.post(f"/api/sessions/{session_id}/messages", json={"text": "How do they pay?"})


def test_a_second_message_within_a_second_gets_429_and_is_not_recorded(
    throttled: TestClient, fake_llm: FakeLLM, clock: list[float]
) -> None:
    session_id = _start(throttled)
    assert _send(throttled, session_id, fake_llm).status_code == 200

    clock[0] += 0.9
    refused = _send(throttled, session_id)

    assert refused.status_code == 429
    assert refused.json()["error"] == {
        "code": "SESSION_RATE_LIMIT",
        "message_key": "errors.SESSION_RATE_LIMIT",
        "detail": "send at most one message every 1 s",
    }
    assert throttled.get(f"/api/sessions/{session_id}").json()["student_turns_used"] == 1
    clock[0] += 0.1  # one second after the first message: the refusal didn't restart it
    assert _send(throttled, session_id, fake_llm).status_code == 200


def test_each_session_has_its_own_interval(throttled: TestClient, fake_llm: FakeLLM) -> None:
    first, second = _start(throttled), _start(throttled)

    assert _send(throttled, first, fake_llm).status_code == 200
    assert _send(throttled, second, fake_llm).status_code == 200


def test_an_interval_of_zero_turns_the_check_off() -> None:
    off = MessageThrottle(0)
    for _ in range(3):
        off.check("s1")
