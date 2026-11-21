"""The disclosure gate: which hidden facts has the student's latest message earned?

The gate model sees fact ids and unlock conditions only, never a fact's content or signal,
and never the transcript (docs/architecture.md, "Rules the tests enforce"). Its answer is
only a suggestion: the rules here decide what actually unlocks. Each unlock must quote, as
evidence, one of that fact's own `unlock_when` behaviours; an unlock whose quote doesn't
match is rejected.
"""

import json
import logging
import time
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from pydantic import BaseModel, Field, field_validator

from app.content import Client, HiddenFact, Product
from app.llm import ChatMessage, LLMClient, LLMError, Role
from app.prompts import PROMPT_VERSION, render

logger = logging.getLogger(__name__)

GATE_MAX_TOKENS = 200
GATE_TEMPERATURE = 0.0
NOTE_LIMIT = 200
_IMPORTANCE_ORDER = {"critical": 0, "important": 1, "minor": 2}


class GateUnlock(BaseModel):
    """One fact the gate says the message earned, with its evidence."""

    id: str
    """The fact's id, from `eligible_facts`."""
    behaviour: str
    """The behaviour the message does, copied word for word from that fact's `unlock_when`."""


class GateDecision(BaseModel):
    """The gate model's answer, before the rules are applied.

    `note` comes first on purpose: the model writes JSON in schema order, so it gives its
    reason before it commits to a decision. With `unlocked` first, a small model sometimes
    unlocked a fact and then explained why the message earned nothing.
    """

    note: str = Field(max_length=NOTE_LIMIT)
    """One short sentence: which `unlock_when` behaviour, if any, the message does. Required,
    so the model can't skip its reasoning."""
    unlocked: list[GateUnlock]
    """The eligible facts the student's message earned, each with its quoted behaviour."""
    products_mentioned: list[str]
    """Catalogue ids the student proposed, recommended or asked about."""

    @field_validator("note", mode="before")
    @classmethod
    def _shorten(cls, value: object) -> object:
        # A long explanation shouldn't cost the whole decision.
        return value[:NOTE_LIMIT] if isinstance(value, str) else value


@dataclass(frozen=True)
class GateOutcome:
    """What the gate decided for one student message, after the rules."""

    eligible: tuple[str, ...]
    """Facts that could unlock this turn: still locked, with every `requires` unlocked."""
    unlocked: tuple[str, ...]
    """Every fact unlocked this turn, in content order."""
    by_pitch: tuple[str, ...]
    """The part of `unlocked` that the product-pitch rule unlocked."""
    products_mentioned: tuple[str, ...]
    note: str
    failed: bool
    latency_ms: int
    rejected: tuple[str, ...] = ()
    """Eligible facts the gate unlocked with a behaviour that isn't in that fact's own
    `unlock_when`, and that stayed locked."""
    quotes: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    """The behaviour quoted for each fact the gate itself unlocked (not the pitch rule)."""


@dataclass(frozen=True)
class Enforced:
    """The gate's suggestion after the rules."""

    by_question: tuple[str, ...]
    by_pitch: tuple[str, ...]
    products: tuple[str, ...]
    rejected: tuple[str, ...]
    quotes: Mapping[str, str]


def eligible_facts(client: Client, unlocked: Collection[str]) -> list[HiddenFact]:
    """Locked facts whose `requires` are all unlocked, in content order."""
    return [
        fact
        for fact in client.hidden_facts
        if fact.id not in unlocked and all(required in unlocked for required in fact.requires)
    ]


def gate_messages(
    *,
    client_reply: str,
    student_message: str,
    eligible: Sequence[HiddenFact],
    others: Sequence[tuple[HiddenFact, str]],
    products: Sequence[Product],
) -> list[ChatMessage]:
    """The gate's instructions, then its input as JSON: ids and conditions, no content.

    `others` are the client's other facts with their status ("already unlocked" or "not
    available yet"). They let the gate see that a message is about a topic it can't unlock
    now, instead of stretching an eligible fact's behaviour to fit.
    """
    data = {
        "client_reply": client_reply,
        "student_message": student_message,
        "eligible_facts": [
            {"id": fact.id, "unlock_when": list(fact.unlock_when)} for fact in eligible
        ],
        "other_facts": [
            {"id": fact.id, "unlock_when": list(fact.unlock_when), "status": status}
            for fact, status in others
        ],
        "catalogue": [
            {
                "id": product.id,
                "name_en": product.name.en,
                "name_ar": product.name.ar,
                "interest_based": product.interest_based,
                "sharia_compliant": product.sharia_compliant,
            }
            for product in products
        ],
    }
    return [
        ChatMessage(role="system", content=render("gate")),
        ChatMessage(role="user", content=json.dumps(data, ensure_ascii=False)),
    ]


def quotes_its_fact(unlock: GateUnlock, fact: HiddenFact) -> bool:
    """True if the quoted behaviour is one of the fact's own `unlock_when` entries, ignoring
    case and surrounding whitespace."""
    quoted = unlock.behaviour.strip().casefold()
    return any(quoted == behaviour.strip().casefold() for behaviour in fact.unlock_when)


def enforce(
    decision: GateDecision,
    eligible: Sequence[HiddenFact],
    product_ids: Collection[str],
    *,
    max_unlocks: int,
) -> Enforced:
    """Apply the rules to the gate's suggestion.

    Only eligible facts and catalogue products count, and an unlock counts only if it quotes
    one of that fact's own `unlock_when` behaviours: otherwise it's rejected. The gate's
    unlocks are capped, keeping critical facts first, then important, then minor, then
    content order. A pitched product also unlocks every eligible fact that reacts to it,
    beyond the cap: that is the client reacting to the pitch, not the student earning a fact.
    """
    facts = {fact.id: fact for fact in eligible}
    position = {fact.id: index for index, fact in enumerate(eligible)}
    rank = {fact.id: _IMPORTANCE_ORDER[fact.importance] for fact in eligible}
    verified: dict[str, str] = {}
    misquoted: list[str] = []
    for unlock in decision.unlocked:
        fact = facts.get(unlock.id)
        if fact is None:
            continue  # not eligible: never unlockable this turn
        if quotes_its_fact(unlock, fact):
            verified.setdefault(fact.id, unlock.behaviour.strip())
        else:
            misquoted.append(fact.id)
    by_question = sorted(verified, key=lambda fact_id: (rank[fact_id], position[fact_id]))
    by_question = by_question[:max_unlocks]
    products = tuple(
        product_id
        for product_id in dict.fromkeys(decision.products_mentioned)
        if product_id in product_ids
    )
    by_pitch = tuple(
        fact.id
        for fact in eligible
        if fact.id not in by_question and set(fact.unlock_on_product_pitch) & set(products)
    )
    unlocked = {*by_question, *by_pitch}
    rejected = tuple(
        fact_id
        for fact_id in dict.fromkeys(misquoted)
        if fact_id not in verified and fact_id not in unlocked
    )
    quotes = MappingProxyType({fact_id: verified[fact_id] for fact_id in by_question})
    return Enforced(tuple(by_question), by_pitch, products, rejected, quotes)


async def run_gate(
    llm: LLMClient,
    *,
    model: str,
    client: Client,
    products: Sequence[Product],
    unlocked: Collection[str],
    client_reply: str,
    student_message: str,
    max_unlocks: int,
) -> GateOutcome:
    """Ask the gate model about one student message, then apply the rules.

    Eligibility is fixed before the call, so a fact that becomes eligible during this turn
    can only unlock on a later one. Any model failure (an `LLMError`, which includes
    `InvalidOutput`) unlocks nothing and mentions no product: the turn goes on without the gate.
    """
    eligible = eligible_facts(client, unlocked)
    eligible_ids = tuple(fact.id for fact in eligible)
    others = [
        (fact, "already unlocked" if fact.id in unlocked else "not available yet")
        for fact in client.hidden_facts
        if fact.id not in eligible_ids
    ]
    messages = gate_messages(
        client_reply=client_reply,
        student_message=student_message,
        eligible=eligible,
        others=others,
        products=products,
    )
    started = time.perf_counter()
    try:
        decision, _ = await llm.chat_json(
            Role.GATE,
            messages,
            GateDecision,
            model=model,
            max_tokens=GATE_MAX_TOKENS,
            temperature=GATE_TEMPERATURE,
            prompt_version=PROMPT_VERSION["gate"],
        )
    except LLMError as exc:
        logger.warning("Gate failed; nothing unlocks this turn", extra={"code": exc.code})
        return GateOutcome(eligible_ids, (), (), (), "", True, _since(started))
    enforced = enforce(
        decision, eligible, {product.id for product in products}, max_unlocks=max_unlocks
    )
    chosen = {*enforced.by_question, *enforced.by_pitch}
    return GateOutcome(
        eligible=eligible_ids,
        unlocked=tuple(fact_id for fact_id in eligible_ids if fact_id in chosen),
        by_pitch=enforced.by_pitch,
        products_mentioned=enforced.products,
        note=decision.note,
        failed=False,
        latency_ms=_since(started),
        rejected=enforced.rejected,
        quotes=enforced.quotes,
    )


def _since(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
