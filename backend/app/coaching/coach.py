"""The AI coach: feedback on a finished interview, grounded in the deterministic analysis.

The model writes the report, then code checks it against the interview: evidence turns must be
the student's own turns, ids must exist, each list keeps at most four items, and every missed
critical need gets an entry even when the model leaves it out (a "backfilled" entry). If the
model fails, there is no report and the feedback is degraded: the analysis stands on its own.

The coach sees the client's whole profile, including facts the student never unlocked. The
interview is over by then, which is why `FeedbackService` runs the coach only after the wrap-up.
"""

import json
import logging
import re
import time
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.coaching.analysis import Analysis, missed_critical_needs, product_verdict
from app.coaching.report import CoachReport, Improvement, MissedPoint, WentWell
from app.content import Client, LocalizedText, Need, Product
from app.llm import ChatMessage, InvalidOutput, LLMClient, LLMError, Role
from app.prompts import PROMPT_VERSION, render
from app.simulation import Language, Session, normalise

logger = logging.getLogger(__name__)

COACH_MAX_TOKENS = 1500
COACH_TEMPERATURE = 0.3
MAX_ITEMS = 4
# Speaker labels in the transcript the model reads: `[t3] Student: …`.
SPEAKERS = {"student": "Student", "client": "Client"}
_LATIN = re.compile(r"[a-z]")


@dataclass(frozen=True)
class Dropped:
    """An item that code removed from the coach's report, and why. Telemetry records `text`
    only with LOG_TRANSCRIPTS."""

    section: str
    reason: str
    text: str


@dataclass(frozen=True)
class Cleared:
    """A field that code set to null, keeping its item: `section.field`, and why."""

    section: str
    field: str
    reason: str


@dataclass(frozen=True)
class Checked:
    """The report after the checks, and what the checks changed."""

    report: CoachReport
    backfilled: tuple[str, ...]
    """Missed critical needs the model left out, added by code (need ids)."""
    dropped: tuple[Dropped, ...] = ()
    cleared: tuple[Cleared, ...] = ()


@dataclass(frozen=True)
class CoachOutcome:
    """One run of the coach. `report` is None when `degraded`."""

    report: CoachReport | None
    degraded: bool
    backfilled: tuple[str, ...]
    """The missed critical needs that the model left out and code added (need ids)."""
    latency_ms: int
    """The whole call, retries and any model swap included."""
    json_retried: bool
    """The model's first reply was unusable JSON, so it was asked once more."""
    error_code: str | None
    generated_at: datetime
    dropped: tuple[Dropped, ...] = ()
    """Items that the checks removed (see `check_report`)."""
    cleared: tuple[Cleared, ...] = ()
    """Fields that the checks set to null (see `check_report`)."""


def localized(text: LocalizedText, language: Language) -> str:
    """The text in `language`, or the English when there's no Arabic."""
    return text.ar if language == "ar" and text.ar else text.en


def coach_input(session: Session, analysis: Analysis, language: Language) -> dict[str, object]:
    """Everything the coach reads, as one JSON-ready object. Raises ValueError without a
    wrap-up."""
    if session.wrapup is None:
        raise ValueError("the session has no wrap-up yet")
    client = session.client
    locked = {fact.fact_id for fact in analysis.facts if fact.unlocked_at_turn is None}
    return {
        "output_language": language,
        "client": _profile(client),
        "coach_notes": client.coach_notes.model_dump(),
        "catalogue": [_product(product) for product in session.products.values()],
        "transcript": [f"[t{turn.n}] {SPEAKERS[turn.role]}: {turn.text}" for turn in session.turns],
        "student_turns": [turn.n for turn in session.turns if turn.role == "student"],
        "wrapup": {
            "summary": session.wrapup.needs_summary,
            "recommendations": [
                {"product_id": item.product_id, "reason": item.reason}
                for item in session.wrapup.recommendations
            ],
        },
        "analysis": analysis.model_dump(mode="json"),
        "example_questions_for_missed_facts": {
            fact.id: list(fact.example_questions)
            for fact in client.hidden_facts
            if fact.id in locked
        },
    }


def coach_messages(session: Session, analysis: Analysis, language: Language) -> list[ChatMessage]:
    """The coach's instructions, then its input as JSON."""
    data = coach_input(session, analysis, language)
    return [
        ChatMessage(role="system", content=render("coach")),
        ChatMessage(role="user", content=json.dumps(data, ensure_ascii=False)),
    ]


async def run_coach(
    llm: LLMClient,
    session: Session,
    analysis: Analysis,
    language: Language,
    *,
    clock: Callable[[], datetime],
) -> CoachOutcome:
    """Ask the coach model for its report on the session, then check it.

    Never raises a model error: any `LLMError` (which includes `InvalidOutput`) gives a
    degraded outcome without a report.
    """
    messages = coach_messages(session, analysis, language)
    started = time.perf_counter()
    try:
        report, result = await llm.chat_json(
            Role.COACH,
            messages,
            CoachReport,
            model=session.models.coach,
            max_tokens=COACH_MAX_TOKENS,
            temperature=COACH_TEMPERATURE,
            prompt_version=PROMPT_VERSION["coach"],
        )
    except LLMError as exc:
        logger.warning("Coach failed; the feedback is degraded", extra={"code": exc.code})
        return CoachOutcome(
            report=None,
            degraded=True,
            backfilled=(),
            latency_ms=_since(started),
            # chat_json gives up with InvalidOutput only after its one retry.
            json_retried=isinstance(exc, InvalidOutput),
            error_code=exc.code,
            generated_at=clock(),
        )
    checked = check_report(report, session=session, analysis=analysis, language=language)
    return CoachOutcome(
        report=checked.report,
        degraded=False,
        backfilled=checked.backfilled,
        latency_ms=_since(started),
        json_retried=result.json_retried,
        error_code=None,
        generated_at=clock(),
        dropped=checked.dropped,
        cleared=checked.cleared,
    )


def check_report(
    report: CoachReport, *, session: Session, analysis: Analysis, language: Language
) -> Checked:
    """The report as the student may see it, and what the checks changed.

    - Evidence turns that aren't the student's own turns are dropped.
    - Praise must be grounded. A `went_well` item is dropped, never rewritten, when it cites
      no student turn, or cites a turn where the student pitched a product that is
      unsuitable, or a turn that a `missed` item cites.
    - A `better_question` or `example` that names a product (its id, its English or Arabic
      name, or an alias) becomes None, and its item stays: those are the student's own
      discovery questions, not pitches.
    - An unknown `need_id` or `product_id` becomes None. Ids are matched ignoring case.
    - Items without text are dropped, and each list keeps its first four items.
    - Every missed critical need without an entry gets one, first in `missed`: the point is
      the need's description, and the better question the first example question of its
      first critical fact still locked. Those entries are never cut.
    """
    student_turns = {turn.n for turn in session.turns if turn.role == "student"}
    names = _product_names(session.products.values())
    cleared: list[Cleared] = []

    def question(text: str | None, section: str, field: str) -> str | None:
        if text and _names_a_product(text, names):
            cleared.append(Cleared(section=section, field=field, reason="names_a_product"))
            return None
        return text or None

    need_ids = _by_folded(need.id for need in session.client.needs)
    product_ids = _by_folded(session.products)

    def turns(values: Sequence[int]) -> list[int]:
        return sorted({n for n in values if n in student_turns})

    missed = [
        MissedPoint(
            point=item.point,
            need_id=_known(item.need_id, need_ids),
            product_id=_known(item.product_id, product_ids),
            evidence_turns=turns(item.evidence_turns),
            better_question=question(item.better_question, "missed", "better_question"),
        )
        for item in report.missed
        if item.point
    ][:MAX_ITEMS]
    covered = {item.need_id for item in missed}
    added = [
        _backfill(need, session.client, analysis, language)
        for need in missed_critical_needs(session.client, analysis)
        if need.id not in covered
    ]
    missed = [*added, *missed][: max(MAX_ITEMS, len(added))]
    unsuitable_pitches = {
        n
        for product_id, pitched in session.products_mentioned.items()
        if product_verdict(session.client, product_id).verdict == "unsuitable"
        for n in pitched
    }
    missed_turns = {n for item in missed for n in item.evidence_turns}
    went_well: list[WentWell] = []
    dropped: list[Dropped] = []
    for praise in report.went_well:
        if not praise.point:
            continue
        cited = turns(praise.evidence_turns)
        reason = _ungrounded(cited, unsuitable_pitches, missed_turns)
        if reason is None:
            went_well.append(WentWell(point=praise.point, evidence_turns=cited))
        else:
            dropped.append(Dropped(section="went_well", reason=reason, text=praise.point))
    how_to_improve = [
        Improvement(tip=item.tip, example=question(item.example, "how_to_improve", "example"))
        for item in report.how_to_improve
        if item.tip
    ][:MAX_ITEMS]
    checked = CoachReport(
        went_well=went_well[:MAX_ITEMS],
        missed=missed,
        how_to_improve=how_to_improve,
        summary_feedback=report.summary_feedback,
    )
    return Checked(
        report=checked,
        backfilled=tuple(item.need_id for item in added if item.need_id is not None),
        dropped=tuple(dropped),
        cleared=tuple(cleared),
    )


def _product_names(products: Iterable[Product]) -> list[str]:
    """Every way to name a product, normalised: its id, its names and its aliases."""
    names = {
        normalise(name)
        for product in products
        for name in (product.id, product.name.en, product.name.ar, *product.aliases)
        if name
    }
    return sorted(names)


def _names_a_product(text: str, names: Sequence[str]) -> bool:
    """True if `text` contains one of `names`. Latin names match whole words only; Arabic names
    match inside a word too, because prefixes such as «ال» and «ب» attach to it."""
    folded = normalise(text)
    for name in names:
        if _LATIN.search(name):
            if re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", folded):
                return True
        elif name in folded:
            return True
    return False


def _ungrounded(
    cited: Sequence[int], unsuitable_pitches: Collection[int], missed_turns: Collection[int]
) -> str | None:
    """Why a `went_well` item isn't grounded in the student's turns, if it isn't."""
    if not cited:
        return "no_student_turn"
    if any(n in unsuitable_pitches for n in cited):
        return "cites_unsuitable_pitch"
    if any(n in missed_turns for n in cited):
        return "cites_missed_turn"
    return None


def _backfill(need: Need, client: Client, analysis: Analysis, language: Language) -> MissedPoint:
    locked = {fact.fact_id for fact in analysis.facts if fact.unlocked_at_turn is None}
    facts = {fact.id: fact for fact in client.hidden_facts}
    first = next(
        facts[fact_id]
        for fact_id in need.evidence_facts
        if fact_id in locked and facts[fact_id].importance == "critical"
    )
    return MissedPoint(
        point=localized(need.description, language),
        need_id=need.id,
        product_id=None,
        evidence_turns=[],
        better_question=first.example_questions[0],
    )


def _profile(client: Client) -> dict[str, object]:
    return {
        "name": client.card.name.en,
        "name_ar": client.card.name.ar,
        "headline": client.card.headline.en,
        "segment": client.segment,
        "persona": client.persona.model_dump(exclude_none=True),
        "open_facts": list(client.open_facts),
        "hidden_facts": [
            {"id": fact.id, "content": fact.content, "importance": fact.importance}
            for fact in client.hidden_facts
        ],
        "needs": [
            {
                "id": need.id,
                "description": need.description.en,
                "description_ar": need.description.ar,
                "evidence_facts": list(need.evidence_facts),
                "suitable_products": list(need.suitable_products),
                "unsuitable_products": [
                    {"id": entry.id, "reason": entry.reason.en, "reason_ar": entry.reason.ar}
                    for entry in need.unsuitable_products
                ],
            }
            for need in client.needs
        ],
        "no_catalogue_fit": client.no_catalogue_fit,
        "referral_note": client.referral_note.en if client.referral_note else None,
    }


def _product(product: Product) -> dict[str, object]:
    return {
        "id": product.id,
        "name_en": product.name.en,
        "name_ar": product.name.ar,
        "sharia_compliant": product.sharia_compliant,
        "interest_based": product.interest_based,
        "summary": product.summary.en,
    }


def _by_folded(ids: Iterable[str]) -> dict[str, str]:
    return {item.casefold(): item for item in ids}


def _known(value: str | None, ids: dict[str, str]) -> str | None:
    return ids.get(value.strip().casefold()) if value else None


def _since(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
