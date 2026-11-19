"""No public endpoint may expose private content before `feedback_ready` (CLAUDE.md rule 3).

Every route in the OpenAPI schema needs an entry in `PUBLIC_CALLS`. A new endpoint therefore
fails `test_every_api_route_is_checked_for_leaks` until it's added here with its leak rules.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.content import ContentRegistry, load_registry
from app.content import store as store_module
from app.llm import llm_dep
from app.llm.fake import FakeLLM
from app.main import create_app
from tests.conftest import SettingsFactory
from tests.content_factory import CLIENT, SECRET_CASH_GAP, ContentDir, client_data
from tests.no_leak import assert_no_leak, find_leaks

# (method, schema path) -> (path to request, keys allowed to use a private key's name)
PUBLIC_CALLS: dict[tuple[str, str], tuple[str, frozenset[str]]] = {
    # `content` here is health's own status of the content files, not a hidden fact.
    ("GET", "/api/health"): ("/api/health", frozenset({"$.content"})),
    ("GET", "/api/bank"): ("/api/bank", frozenset()),
    ("GET", "/api/clients"): ("/api/clients", frozenset()),
    ("GET", "/api/products"): ("/api/products", frozenset()),
}


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


@pytest.mark.parametrize("route", list(PUBLIC_CALLS), ids=lambda route: " ".join(route))
def test_public_responses_carry_no_private_content(
    client: TestClient, real_registry: ContentRegistry, route: tuple[str, str]
) -> None:
    path, allowed_keys = PUBLIC_CALLS[route]
    response = client.request(route[0], path)
    assert response.status_code == 200
    assert_no_leak(response.json(), real_registry, allowed_keys=allowed_keys)


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
