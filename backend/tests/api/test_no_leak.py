"""No public endpoint may expose private content before `feedback_ready` (CLAUDE.md rule 3).

Every route in the OpenAPI schema needs an entry in `PUBLIC_CALLS`. A new endpoint therefore
fails `test_every_api_route_is_checked_for_leaks` until it's added here with its leak rules.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.content import ContentRegistry, load_registry
from app.content import store as store_module
from app.llm import Role, llm_dep
from app.llm.fake import FakeLLM
from app.main import create_app
from tests.conftest import SettingsFactory
from tests.content_factory import CLIENT, SECRET_CASH_GAP, ContentDir, client_data
from tests.interview_factory import gate_reply
from tests.no_leak import assert_no_leak, find_leaks

NOURA = "noura-al-kuwari"
SESSION = "/api/sessions/{session_id}"


@dataclass(frozen=True)
class PublicCall:
    """How to call one route for the leak check.

    For a session route, a session with Noura is started first and `turns` scripted messages
    are sent, each unlocking one of her hidden facts, so the session has private state to leak.
    """

    path: str
    body: dict[str, Any] | None = None
    status: int = 200
    turns: int = 0
    unlocks: bool = False  # the call itself is a message that unlocks a fact
    allowed_keys: frozenset[str] = field(default_factory=frozenset)


PUBLIC_CALLS: dict[tuple[str, str], PublicCall] = {
    # `content` here is health's own status of the content files, not a hidden fact.
    ("GET", "/api/health"): PublicCall("/api/health", allowed_keys=frozenset({"$.content"})),
    ("GET", "/api/bank"): PublicCall("/api/bank"),
    ("GET", "/api/clients"): PublicCall("/api/clients"),
    ("GET", "/api/products"): PublicCall("/api/products"),
    ("POST", "/api/sessions"): PublicCall(
        "/api/sessions", body={"client_id": NOURA, "language": "en"}, status=201
    ),
    ("GET", SESSION): PublicCall(SESSION, turns=2),
    ("POST", f"{SESSION}/messages"): PublicCall(
        f"{SESSION}/messages",
        body={"text": "Is Islamic banking important to you?"},
        turns=1,
        unlocks=True,
    ),
    ("POST", f"{SESSION}/wrapup"): PublicCall(
        f"{SESSION}/wrapup",
        body={
            "needs_summary": "She is paid late by government clients and needs Islamic finance.",
            "recommendations": [
                {"product_id": "murabaha-working-capital", "reason": "Sharia-compliant stock."}
            ],
        },
        turns=2,
    ),
    ("DELETE", SESSION): PublicCall(SESSION, status=204, turns=1),
}

# The order the scripted messages unlock Noura's facts in (each one's `requires` first).
NOURA_UNLOCKS = ("late-payments", "sharia-only", "big-contract")


@pytest.fixture
def real_registry(settings: Settings) -> ContentRegistry:
    """The repository's own content, which the default `client` fixture serves."""
    return load_registry(settings.CONTENT_DIR)


def test_every_api_route_is_checked_for_leaks(client: TestClient) -> None:
    schema = client.get("/api/openapi.json").json()
    routes = {
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        for method in operations
    }
    assert routes == set(PUBLIC_CALLS), "add new routes to PUBLIC_CALLS with their leak rules"


def _script_turn(fake: FakeLLM, fact_id: str) -> None:
    fake.script(Role.GATE, gate_reply(fact_id))
    fake.script(Role.CLIENT, "Let me think about how to put this.")


def _prepare(client: TestClient, fake: FakeLLM, call: PublicCall) -> str:
    """Start a session and send the setup turns, if the route needs them; return its path."""
    if "{session_id}" not in call.path:
        return call.path
    created = client.post("/api/sessions", json={"client_id": NOURA, "language": "en"})
    session_id = created.json()["session_id"]
    for index in range(call.turns):
        _script_turn(fake, NOURA_UNLOCKS[index])
        sent = client.post(f"/api/sessions/{session_id}/messages", json={"text": f"Q{index}?"})
        assert sent.status_code == 200, sent.text
    if call.unlocks:
        _script_turn(fake, NOURA_UNLOCKS[call.turns])
    return call.path.format(session_id=session_id)


@pytest.mark.parametrize("route", list(PUBLIC_CALLS), ids=lambda route: " ".join(route))
def test_public_responses_carry_no_private_content(
    client: TestClient, fake_llm: FakeLLM, real_registry: ContentRegistry, route: tuple[str, str]
) -> None:
    call = PUBLIC_CALLS[route]
    path = _prepare(client, fake_llm, call)

    response = client.request(route[0], path, json=call.body)

    assert response.status_code == call.status, response.text
    if call.status == 204:
        assert response.content == b""
        return
    assert_no_leak(response.json(), real_registry, allowed_keys=call.allowed_keys)


def test_the_helper_catches_private_keys_and_hidden_facts(real_registry: ContentRegistry) -> None:
    secret = real_registry.get_client("noura-al-kuwari").hidden_facts[0].content

    leaks = find_leaks({"persona": {}, "turns": [{"text": f"I said: {secret}"}]}, real_registry)

    assert leaks == [
        "$.persona: private key 'persona'",
        f"$.turns[0].text: contains a hidden fact ({secret[:30]}...)",
    ]
    assert find_leaks({"content": {"ok": True}}, real_registry, allowed_keys={"$.content"}) == []
    assert find_leaks({"x": {"content": "a"}}, real_registry, allowed_keys={"$.content"}) != []


@pytest.fixture
def broken_after_startup(
    content: ContentDir,
    settings_factory: SettingsFactory,
    fake_llm: FakeLLM,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, ContentRegistry]]:
    """The app, and its last good content, after the files broke where error text could
    quote a hidden fact: a YAML syntax error on a hidden fact's line, and a hidden fact's
    text as a rejected value."""
    clock = [1000.0]
    monkeypatch.setattr(store_module, "_now", lambda: clock[0])
    settings = settings_factory(CONTENT_DIR=content.root, FRONTEND_DIST=tmp_path / "missing")
    app = create_app(settings)
    app.dependency_overrides[llm_dep] = lambda: fake_llm
    last_good = load_registry(content.root)

    content.write_text("clients/second.yaml", f"id: second\ncontent: {SECRET_CASH_GAP}\n")
    rejected = client_data()
    rejected["hidden_facts"][1]["importance"] = SECRET_CASH_GAP
    content.write(f"clients/{CLIENT}.yaml", rejected)
    clock[0] += 2
    with TestClient(app) as test_client:
        yield test_client, last_good


def test_content_errors_in_health_carry_no_private_content(
    broken_after_startup: tuple[TestClient, ContentRegistry],
) -> None:
    api, last_good = broken_after_startup

    health = api.get("/api/health").json()

    assert health["content"]["ok"] is False
    assert len(health["content"]["errors"]) == 2
    assert SECRET_CASH_GAP not in str(health)
    assert_no_leak(health, last_good, allowed_keys={"$.content"})
