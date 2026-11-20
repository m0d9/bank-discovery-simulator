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
from tests.coaching_factory import coach_reply
from tests.conftest import SettingsFactory
from tests.content_factory import CLIENT, SECRET_CASH_GAP, ContentDir, client_data
from tests.interview_factory import gate_reply, real_quote
from tests.no_leak import assert_no_leak, find_leaks, find_text_leaks

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
    wrap_up: bool = False  # the session is wrapped up after the setup turns
    reveals: bool = False  # the one response allowed to carry private content
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
    # Feedback reveals the private profile: that's what it's for (see the test below).
    ("POST", f"{SESSION}/feedback"): PublicCall(
        f"{SESSION}/feedback?lang=en", turns=2, wrap_up=True, reveals=True
    ),
    # Before feedback, the export holds the transcript and the wrap-up only.
    ("GET", f"{SESSION}/export"): PublicCall(f"{SESSION}/export", turns=2, wrap_up=True),
}
WRAPUP_BODY = PUBLIC_CALLS[("POST", f"{SESSION}/wrapup")].body

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
    fake.script(Role.GATE, gate_reply(real_quote(fact_id)))
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
    if call.wrap_up:
        wrapped = client.post(f"/api/sessions/{session_id}/wrapup", json=WRAPUP_BODY)
        assert wrapped.status_code == 200, wrapped.text
    if call.reveals:
        fake.script(Role.COACH, coach_reply())
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
    if call.reveals:
        assert find_leaks(response.json(), real_registry), "feedback should reveal the profile"
        return
    if response.headers["content-type"].startswith("text/markdown"):
        assert find_text_leaks(response.text, real_registry) == []
        return
    assert_no_leak(response.json(), real_registry, allowed_keys=call.allowed_keys)


def test_after_feedback_only_the_feedback_and_the_export_carry_private_content(
    client: TestClient, fake_llm: FakeLLM, real_registry: ContentRegistry
) -> None:
    feedback_path = _prepare(client, fake_llm, PUBLIC_CALLS[("POST", f"{SESSION}/feedback")])
    session_path = feedback_path.removesuffix("/feedback?lang=en")
    feedback = client.post(feedback_path)
    assert feedback.status_code == 200, feedback.text

    assert_no_leak(client.get(session_path).json(), real_registry)
    late_message = client.post(f"{session_path}/messages", json={"text": "One more thing?"})
    assert late_message.status_code == 409
    assert_no_leak(late_message.json(), real_registry)
    assert find_text_leaks(client.get(f"{session_path}/export").text, real_registry) != []


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
