"""Deterministic analysis of a finished interview. No model is involved.

For each need: whether the student uncovered it. For each hidden fact: when it came out, and
whether a question or a product pitch brought it out. For each recommended product: its verdict
against the client's answer key. Then the suitable products the student didn't recommend, and a
few counts. The coach explains this analysis and must never contradict it.
"""

from collections.abc import Collection, Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.content import Client, Importance, LocalizedText, Need
from app.simulation import Session, Turn

NeedStatus = Literal["uncovered", "partial", "missed"]
Verdict = Literal["suitable", "unsuitable", "not_in_key"]
DiscoveredBy = Literal["question", "product_pitch"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class FactUnlock(_Frozen):
    """One evidence fact of a need, and the student turn that unlocked it."""

    fact_id: str
    unlocked_at_turn: int | None


class Via(_Frozen):
    """The student turn whose unlock completed a need, and what the student said in it."""

    turn: int
    question: str


class NeedResult(_Frozen):
    """`uncovered` when every evidence fact is unlocked, `partial` when some are, `missed`
    when none are. `via` is set only for an uncovered need."""

    need_id: str
    status: NeedStatus
    facts: tuple[FactUnlock, ...]
    via: Via | None


class FactResult(_Frozen):
    """When a hidden fact came out (`None` if it never did), and what brought it out."""

    fact_id: str
    importance: Importance
    unlocked_at_turn: int | None
    discovered_by: DiscoveredBy | None


class VerdictReason(_Frozen):
    """Why a product is unsuitable: for one need, or (`need_id` None) the referral note."""

    need_id: str | None
    reason: LocalizedText


class ProductVerdict(_Frozen):
    """A recommended product against the answer key. `reasons` are set when it's
    unsuitable, `needs` (the needs it fits) when it's suitable."""

    product_id: str
    verdict: Verdict
    reasons: tuple[VerdictReason, ...]
    needs: tuple[str, ...]


class MissedOpportunity(_Frozen):
    """A suitable product the student didn't recommend, and the needs it would have met."""

    product_id: str
    needs: tuple[str, ...]


class Stats(_Frozen):
    """Counts, never scores."""

    student_turns: int
    needs_uncovered: int
    needs_total: int
    critical_found: int
    critical_total: int
    first_unlock_turn: int | None


class Analysis(_Frozen):
    """Everything the code can say about an interview without a model."""

    needs: tuple[NeedResult, ...]
    facts: tuple[FactResult, ...]
    products: tuple[ProductVerdict, ...]
    missed_opportunities: tuple[MissedOpportunity, ...]
    stats: Stats


def analyse(session: Session) -> Analysis:
    """Analyse a wrapped-up session against its client's answer key.

    Works on the session's own snapshot of the client, never on reloaded content. Raises
    ValueError if the session has no wrap-up yet.
    """
    if session.wrapup is None:
        raise ValueError("the session has no wrap-up yet")
    client = session.client
    turns = {turn.n: turn for turn in session.turns}
    by_pitch = {fact_id for turn in session.turns for fact_id in turn.unlocked_by_pitch}
    facts = tuple(
        FactResult(
            fact_id=fact.id,
            importance=fact.importance,
            unlocked_at_turn=session.unlocked.get(fact.id),
            discovered_by=_discovered_by(fact.id, session.unlocked, by_pitch),
        )
        for fact in client.hidden_facts
    )
    needs = tuple(_need_result(need, session.unlocked, turns) for need in client.needs)
    recommended = [item.product_id for item in session.wrapup.recommendations]
    critical = [fact for fact in facts if fact.importance == "critical"]
    return Analysis(
        needs=needs,
        facts=facts,
        products=tuple(product_verdict(client, product_id) for product_id in recommended),
        missed_opportunities=missed_opportunities(client, needs, recommended),
        stats=Stats(
            student_turns=session.student_turns_used,
            needs_uncovered=sum(1 for need in needs if need.status == "uncovered"),
            needs_total=len(needs),
            critical_found=sum(1 for fact in critical if fact.unlocked_at_turn is not None),
            critical_total=len(critical),
            first_unlock_turn=min(session.unlocked.values(), default=None),
        ),
    )


def product_verdict(client: Client, product_id: str) -> ProductVerdict:
    """The verdict on one recommended product.

    Precedence: `unsuitable` if any need lists it as unsuitable; otherwise `suitable` if any
    need lists it as suitable; otherwise `not_in_key`. For a client with `no_catalogue_fit`,
    every product is unsuitable, with the referral note as the reason.
    """
    if client.no_catalogue_fit:
        referral = (
            (VerdictReason(need_id=None, reason=client.referral_note),)
            if client.referral_note is not None
            else ()
        )
        return ProductVerdict(
            product_id=product_id, verdict="unsuitable", reasons=referral, needs=()
        )
    reasons = tuple(
        VerdictReason(need_id=need.id, reason=entry.reason)
        for need in client.needs
        for entry in need.unsuitable_products
        if entry.id == product_id
    )
    if reasons:
        return ProductVerdict(
            product_id=product_id, verdict="unsuitable", reasons=reasons, needs=()
        )
    fits = tuple(need.id for need in client.needs if product_id in need.suitable_products)
    verdict: Verdict = "suitable" if fits else "not_in_key"
    return ProductVerdict(product_id=product_id, verdict=verdict, reasons=(), needs=fits)


def missed_opportunities(
    client: Client, needs: Sequence[NeedResult], recommended: Collection[str]
) -> tuple[MissedOpportunity, ...]:
    """Suitable products for uncovered or partly uncovered needs that weren't recommended.

    A product that is unsuitable for any need is never listed: recommending it would have
    earned the `unsuitable` verdict, so it can't be a missed opportunity.
    """
    if client.no_catalogue_fit:
        return ()
    status = {result.need_id: result.status for result in needs}
    unsuitable = {entry.id for need in client.needs for entry in need.unsuitable_products}
    found: dict[str, list[str]] = {}
    for need in client.needs:
        if status[need.id] == "missed":
            continue
        for product_id in need.suitable_products:
            if product_id not in recommended and product_id not in unsuitable:
                found.setdefault(product_id, []).append(need.id)
    return tuple(
        MissedOpportunity(product_id=product_id, needs=tuple(need_ids))
        for product_id, need_ids in found.items()
    )


def missed_critical_needs(client: Client, analysis: Analysis) -> list[Need]:
    """Needs with at least one critical evidence fact still locked, in content order.

    These are the needs the coach must always address. A partly uncovered need counts: the
    student missed something critical in it.
    """
    locked = {
        fact.fact_id
        for fact in analysis.facts
        if fact.importance == "critical" and fact.unlocked_at_turn is None
    }
    return [need for need in client.needs if any(fact in locked for fact in need.evidence_facts)]


def _discovered_by(
    fact_id: str, unlocked: Mapping[str, int], by_pitch: Collection[str]
) -> DiscoveredBy | None:
    if fact_id not in unlocked:
        return None
    return "product_pitch" if fact_id in by_pitch else "question"


def _need_result(need: Need, unlocked: Mapping[str, int], turns: Mapping[int, Turn]) -> NeedResult:
    facts = tuple(
        FactUnlock(fact_id=fact_id, unlocked_at_turn=unlocked.get(fact_id))
        for fact_id in need.evidence_facts
    )
    found = [fact.unlocked_at_turn for fact in facts if fact.unlocked_at_turn is not None]
    if len(found) < len(facts):
        return NeedResult(
            need_id=need.id, status="partial" if found else "missed", facts=facts, via=None
        )
    completed = max(found)
    turn = turns.get(completed)
    via = Via(turn=completed, question=turn.text) if turn is not None else None
    return NeedResult(need_id=need.id, status="uncovered", facts=facts, via=via)
