"""Builders for interview tests: content models from the content factory, sessions, gate replies."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from app.content import Bank, Client, ContentRegistry, Product
from app.simulation.models import Language, Session, SessionModels, Turn
from tests.content_factory import CLIENT, bank_data, client_data, deposit_data, product_data

T0 = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
OPENING = "Hello, I have a few minutes."


def registry(*clients: dict[str, Any]) -> ContentRegistry:
    """A registry of the factory's bank and two products, and `clients` (default: the test
    client), built in memory without files."""
    return ContentRegistry(
        Bank.model_validate(bank_data()),
        [Product.model_validate(product_data()), Product.model_validate(deposit_data())],
        [Client.model_validate(data) for data in clients or (client_data(),)],
    )


def make_session(
    session_id: str = "s1",
    *,
    client: Client | None = None,
    at: datetime = T0,
    language: Language = "en",
) -> Session:
    """A new session at turn 0 with the factory's content."""
    content = registry()
    chosen = client or content.get_client(CLIENT)
    return Session(
        id=session_id,
        client_id=chosen.id,
        language=language,
        models=SessionModels(gate="gate-model", client="client-model", coach="coach-model"),
        turns=[Turn(n=0, role="client", text=OPENING, ts=at)],
        created_at=at,
        last_active_at=at,
        client=chosen,
        bank=content.bank,
        products={product.id: product for product in content.list_products()},
    )


def gate_reply(*unlocked: str, products: Sequence[str] = (), note: str = "") -> dict[str, Any]:
    """What the gate model answers, as FakeLLM serves it."""
    return {"unlocked": list(unlocked), "products_mentioned": list(products), "note": note}


def hidden_fact(
    fact_id: str,
    *,
    importance: str = "critical",
    requires: Sequence[str] = (),
    pitch: Sequence[str] = (),
    signal: str | None = None,
) -> dict[str, Any]:
    """A hidden fact whose content and signal are marker text that leak tests search for."""
    data: dict[str, Any] = {
        "id": fact_id,
        "content": f"SECRET-{fact_id.upper()}: the content of {fact_id}.",
        "unlock_when": [f"asks about {fact_id}"],
        "unlock_on_product_pitch": list(pitch),
        "requires": list(requires),
        "importance": importance,
        "example_questions": [f"Tell me about {fact_id}?"],
    }
    if signal is not None:
        data["signal"] = signal
    return data


def client_with(*facts: dict[str, Any]) -> Client:
    """The factory's test client, with these hidden facts instead of its own."""
    data = client_data(hidden_facts=list(facts))
    data["needs"][0]["evidence_facts"] = [facts[0]["id"]]
    return Client.model_validate(data)
