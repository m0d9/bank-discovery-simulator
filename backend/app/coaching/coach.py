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
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.coaching.analysis import Analysis, missed_critical_needs
from app.coaching.report import CoachReport, Improvement, MissedPoint, WentWell
from app.content import Client, LocalizedText, Need, Product
from app.llm import ChatMessage, InvalidOutput, LLMClient, LLMError, Role
from app.prompts import PROMPT_VERSION, render
from app.simulation import Language, Session

logger = logging.getLogger(__name__)

COACH_MAX_TOKENS = 1500
COACH_TEMPERATURE = 0.3
MAX_ITEMS = 4
# Speaker labels in the transcript the model reads: `[t3] Student: …`.
SPEAKERS = {"student": "Student", "client": "Client"}


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
    checked, backfilled = check_report(
        report, session=session, analysis=analysis, language=language
    )
    return CoachOutcome(
        report=checked,
        degraded=False,
        backfilled=backfilled,
        latency_ms=_since(started),
        json_retried=result.json_retried,
        error_code=None,
        generated_at=clock(),
    )


def check_report(
    report: CoachReport, *, session: Session, analysis: Analysis, language: Language
) -> tuple[CoachReport, tuple[str, ...]]:
    """The report as the student may see it, and the ids of the needs added to it.

    - Evidence turns that aren't the student's own turns are dropped.
    - An unknown `need_id` or `product_id` becomes None. Ids are matched ignoring case.
    - Items without text are dropped, and each list keeps its first four items.
    - Every missed critical need without an entry gets one, first in `missed`: the point is
      the need's description, and the better question the first example question of its
      first critical fact still locked. Those entries are never cut.
    """
    student_turns = {turn.n for turn in session.turns if turn.role == "student"}
    need_ids = _by_folded(need.id for need in session.client.needs)
    product_ids = _by_folded(session.products)

    def turns(values: Sequence[int]) -> list[int]:
        return sorted({n for n in values if n in student_turns})

    went_well = [
        WentWell(point=item.point, evidence_turns=turns(item.evidence_turns))
        for item in report.went_well
        if item.point
    ][:MAX_ITEMS]
    missed = [
        MissedPoint(
            point=item.point,
            need_id=_known(item.need_id, need_ids),
            product_id=_known(item.product_id, product_ids),
            evidence_turns=turns(item.evidence_turns),
            better_question=item.better_question or None,
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
    how_to_improve = [
        Improvement(tip=item.tip, example=item.example or None)
        for item in report.how_to_improve
        if item.tip
    ][:MAX_ITEMS]
    checked = CoachReport(
        went_well=went_well,
        missed=missed,
        how_to_improve=how_to_improve,
        summary_feedback=report.summary_feedback,
    )
    return checked, tuple(item.need_id for item in added if item.need_id is not None)


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
