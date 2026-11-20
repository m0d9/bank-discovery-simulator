"""Builders for coaching tests: a client with two needs, finished interviews, coach replies."""

from collections.abc import Mapping, Sequence
from typing import Any

from app.content import Client, load_registry
from app.simulation import Recommendation, Session, Turn, WrapUp
from tests.content_factory import ALPHA, BETA
from tests.interview_factory import (
    REPO_CONTENT,
    T0,
    client_data_with,
    hidden_fact,
    make_session,
)

NOT_IN_KEY = "gamma-card"
"""A product id that the test client's answer key doesn't mention."""

# One step of an interview: the student's message, the facts it unlocked, and the part of
# those that a product pitch unlocked.
Step = tuple[str, Sequence[str], Sequence[str]]

ASK_PAYMENTS: Step = ("How do your customers pay?", ["cash-gap"], [])
ASK_SHARIA: Step = ("Is Islamic banking important to you?", ["sharia"], [])
ASK_PLANS: Step = ("What are your plans?", ["expansion"], [])
SMALL_TALK: Step = ("Tell me about yourself.", [], [])


def coaching_client_data(**overrides: Any) -> dict[str, Any]:
    """Two needs. ALPHA is unsuitable for `fund-gap` but suitable for `grow`; BETA suits both.

    `cash-gap` and `sharia` are critical; `expansion` is important and needs `cash-gap`.
    `sharia` also unlocks when the student pitches ALPHA, as a reaction to the pitch.
    """
    data = client_data_with(
        hidden_fact("cash-gap"),
        hidden_fact("sharia", pitch=[ALPHA]),
        hidden_fact("expansion", importance="important", requires=["cash-gap"]),
    )
    data["needs"] = [
        {
            "id": "fund-gap",
            "description": {"en": "Fund the gap.", "ar": "تمويل الفجوة."},
            "evidence_facts": ["cash-gap", "sharia"],
            "suitable_products": [BETA],
            "unsuitable_products": [{"id": ALPHA, "reason": "Interest-based."}],
        },
        {
            "id": "grow",
            "description": "Grow the business.",
            "evidence_facts": ["expansion"],
            "suitable_products": [ALPHA, BETA],
            "unsuitable_products": [],
        },
    ]
    data.update(overrides)
    return data


def add_steps(session: Session, steps: Sequence[Step]) -> None:
    """Append each step to the session as a student turn and a client reply."""
    for text, unlocked, by_pitch in steps:
        n = session.turns[-1].n + 1
        session.turns.append(
            Turn(
                n=n,
                role="student",
                text=text,
                ts=T0,
                unlocked=list(unlocked),
                unlocked_by_pitch=list(by_pitch),
            )
        )
        session.turns.append(Turn(n=n + 1, role="client", text="I see.", ts=T0))
        session.unlocked.update(dict.fromkeys(unlocked, n))


def wrap_up(*product_ids: str) -> WrapUp:
    """A wrap-up recommending `product_ids`."""
    return WrapUp(
        needs_summary="The client needs to bridge late payments and grow.",
        recommendations=[Recommendation(product_id=pid, reason="It fits.") for pid in product_ids],
    )


def interview(*steps: Step, recommend: Sequence[str], session_id: str = "s1") -> Session:
    """A wrapped-up session with the coaching client (status still `interviewing`: the tests
    that need the status set it)."""
    session = make_session(session_id, client=Client.model_validate(coaching_client_data()))
    add_steps(session, steps)
    session.wrapup = wrap_up(*recommend)
    return session


def real_interview(
    client_id: str,
    *steps: Step,
    recommend: Sequence[str],
    pitched: Mapping[str, Sequence[int]] | None = None,
) -> Session:
    """A wrapped-up session with one of the repository's own clients and the real catalogue.
    `pitched` maps product ids to the student turns that proposed them."""
    content = load_registry(REPO_CONTENT)
    session = make_session(client=content.get_client(client_id))
    session.bank = content.bank
    session.products = {product.id: product for product in content.list_products()}
    add_steps(session, steps)
    session.products_mentioned = {pid: list(turns) for pid, turns in (pitched or {}).items()}
    session.wrapup = wrap_up(*recommend)
    return session


def coach_reply(
    *,
    went_well: Sequence[dict[str, Any]] = (),
    missed: Sequence[dict[str, Any]] = (),
    how_to_improve: Sequence[dict[str, Any]] = (),
    summary: str = "Your summary names the cash gap.",
) -> dict[str, Any]:
    """What the coach model answers, as FakeLLM serves it."""
    return {
        "went_well": list(went_well),
        "missed": list(missed),
        "how_to_improve": list(how_to_improve),
        "summary_feedback": summary,
    }


def missed_item(
    point: str = "You didn't ask about growth.",
    *,
    need_id: str | None = None,
    product_id: str | None = None,
    evidence_turns: Sequence[int] = (),
    better_question: str | None = "What are your plans?",
) -> dict[str, Any]:
    """One `missed` entry as the model writes it."""
    return {
        "point": point,
        "need_id": need_id,
        "product_id": product_id,
        "evidence_turns": list(evidence_turns),
        "better_question": better_question,
    }
