"""The judge: one fixed model (`judge` in configs.yaml) for what code can't check.

- (a) and (b), one call per adversarial session: for each client reply, whether it breaks
  character, and which facts that were still locked it reveals.
- (c), one call per coach report: whether each `went_well` point, each `missed` point and the
  summary feedback is supported by the transcript, the summary and the analysis. Backfilled
  entries are code's own text (a need's description), so they aren't judged.
- (d), one call per Arabic report: how it addresses the student, and whether it matches the
  client's grammatical gender.

A failed call leaves its items unjudged, never passed. The prompts are `evals/prompts/*.md`,
kept apart from the app's prompts so that tuning the app can't change the judge.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from string import Template
from types import MappingProxyType
from typing import Any, Literal

from pydantic import BaseModel

from app.coaching import Feedback
from app.coaching.coach import SPEAKERS
from app.content import Client, LocalizedText
from app.llm import ChatMessage, LLMClient, LLMError, Role
from app.simulation import Session
from evals.configs import JudgeConfig
from evals.records import ArabicJudgement, ItemJudgement, ReplyJudgement

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
JUDGE_TEMPERATURE = 0.0

Category = Literal[
    "praise_not_shown",
    "summary_has_it",
    "already_said_or_asked",
    "invented",
    "contradicts_analysis",
    "other",
]


def _load() -> tuple[dict[str, str], dict[str, str]]:
    texts: dict[str, str] = {}
    versions: dict[str, str] = {}
    for path in sorted(PROMPTS_DIR.glob("*.md")):
        data = path.read_bytes()
        template = Template(data.decode("utf-8"))
        if not template.is_valid() or template.get_identifiers():
            raise ValueError(f"judge prompt {path.name} must have no `$` placeholders")
        texts[path.stem] = template.template
        versions[path.stem] = hashlib.sha256(data).hexdigest()[:8]
    return texts, versions


_PROMPTS, _VERSIONS = _load()
JUDGE_PROMPT_VERSION: Mapping[str, str] = MappingProxyType(_VERSIONS)
"""Prompt name -> the first 8 hex characters of its file's sha256."""


class _Reveal(BaseModel):
    fact_id: str
    evidence: str


class _Reply(BaseModel):
    turn: int
    note: str
    breaks_character: bool
    revealed: list[_Reveal]


class _Replies(BaseModel):
    replies: list[_Reply]


class _Item(BaseModel):
    index: int
    reason: str
    supported: bool
    category: Category | None


class _Items(BaseModel):
    items: list[_Item]


class _StudentLabel(BaseModel):
    id: int
    address: Literal["neutral", "masculine", "feminine"]
    evidence: str


class _ClientLabel(BaseModel):
    id: int
    agreement: Literal["matches", "mismatch", "none"]
    evidence: str


class _ArabicLabels(BaseModel):
    student: list[_StudentLabel]
    client: list[_ClientLabel]


class Judge:
    """Asks the judge model, and turns its answers into records. Never raises a model error:
    a failure comes back as the error code, with the items unjudged."""

    def __init__(self, llm: LLMClient, config: JudgeConfig) -> None:
        self._llm = llm
        self._config = config

    @property
    def model(self) -> str:
        """The judge's model."""
        return self._config.model

    async def replies(self, session: Session) -> tuple[list[ReplyJudgement], str | None]:
        """(a) and (b) for every client reply of an adversarial session."""
        data = replies_input(session)
        turns = [entry["turn"] for entry in data["turns"]]
        try:
            answer = await self._ask("judge_reply", data, _Replies)
        except LLMError as exc:
            return [ReplyJudgement(n=n, judged=False) for n in turns], exc.code
        locked = {entry["turn"]: set(entry["locked"]) for entry in data["turns"]}
        return [
            _reply_judgement(n, verdict, locked[n]) for n, verdict in _match(turns, answer)
        ], None

    async def grounding(
        self, session: Session, feedback: Feedback
    ) -> tuple[list[ItemJudgement], str | None]:
        """(c) for every judged item of the coach's report."""
        items = grounding_items(feedback)
        if not items:
            return [], None
        try:
            answer = await self._ask(
                "judge_grounding", grounding_input(session, feedback, items), _Items
            )
        except LLMError as exc:
            return items, exc.code
        verdicts = {verdict.index: verdict for verdict in answer.items}
        judged: list[ItemJudgement] = []
        for position, item in enumerate(items):
            verdict = verdicts.get(position)
            if verdict is None:
                judged.append(item)
                continue
            category = None if verdict.supported else (verdict.category or "other")
            judged.append(
                item.model_copy(
                    update={
                        "supported": verdict.supported,
                        "category": category,
                        "reason": verdict.reason,
                    }
                )
            )
        return judged, None

    async def arabic(
        self, session: Session, feedback: Feedback
    ) -> tuple[ArabicJudgement | None, str | None]:
        """(d) for an Arabic report: each text labelled by the judge, combined here."""
        data = arabic_input(session, feedback)
        try:
            answer = await self._ask("judge_arabic", data, _ArabicLabels)
        except LLMError as exc:
            return None, exc.code
        return combine_arabic(answer, len(data["to_student"]), len(data["to_client"])), None

    async def _ask[T: BaseModel](self, name: str, data: object, schema: type[T]) -> T:
        messages = [
            ChatMessage(role="system", content=_PROMPTS[name]),
            ChatMessage(role="user", content=json.dumps(data, ensure_ascii=False)),
        ]
        value, _ = await self._llm.chat_json(
            Role.COACH,
            messages,
            schema,
            model=self._config.model,
            max_tokens=self._config.max_tokens,
            temperature=JUDGE_TEMPERATURE,
            prompt_version=f"{name}:{JUDGE_PROMPT_VERSION[name]}",
        )
        return value


def locked_after(session: Session, n: int) -> list[str]:
    """The facts still locked once student turn `n` was handled (content order)."""
    return [
        fact.id
        for fact in session.client.hidden_facts
        if session.unlocked.get(fact.id) is None or session.unlocked[fact.id] > n
    ]


def replies_input(session: Session) -> dict[str, Any]:
    """What the judge reads for (a) and (b): the private facts, and each attack with its reply."""
    client = session.client
    replies = {turn.n: turn.text for turn in session.turns if turn.role == "client"}
    turns = [
        {
            "turn": turn.n + 1,
            "student": turn.text,
            "reply": replies.get(turn.n + 1, ""),
            "locked": locked_after(session, turn.n),
        }
        for turn in session.turns
        if turn.role == "student"
    ]
    return {
        "client": {"name": client.card.name.en, "open_facts": list(client.open_facts)},
        "private_facts": [
            {"id": fact.id, "content": fact.content, "hint": fact.signal}
            for fact in client.hidden_facts
        ],
        "turns": turns,
    }


def grounding_items(feedback: Feedback) -> list[ItemJudgement]:
    """The report's items to judge, unjudged: every praise point, every `missed` point except
    the backfilled entries (code writes those first), and the summary feedback."""
    report = feedback.report
    if report is None:
        return []
    backfilled = len(feedback.backfilled)
    items = [
        ItemJudgement(
            section="went_well", index=index, text=item.point, evidence_turns=item.evidence_turns
        )
        for index, item in enumerate(report.went_well)
    ]
    items += [
        ItemJudgement(
            section="missed", index=index, text=item.point, evidence_turns=item.evidence_turns
        )
        for index, item in enumerate(report.missed)
        if index >= backfilled
    ]
    items.append(ItemJudgement(section="summary_feedback", index=0, text=report.summary_feedback))
    return items


def grounding_input(
    session: Session, feedback: Feedback, items: Sequence[ItemJudgement]
) -> dict[str, object]:
    """What the judge reads for (c): the interview's records and the items, numbered."""
    if session.wrapup is None:
        raise ValueError("the session has no wrap-up")
    client = session.client
    names = {pid: product.name for pid, product in session.products.items()}
    return {
        "transcript": [f"[t{turn.n}] {SPEAKERS[turn.role]}: {turn.text}" for turn in session.turns],
        "student_turns": [turn.n for turn in session.turns if turn.role == "student"],
        "wrapup": {
            "summary": session.wrapup.needs_summary,
            "recommended": [
                {"product": names[item.product_id].en, "reason": item.reason}
                for item in session.wrapup.recommendations
            ],
        },
        "analysis": feedback.analysis.model_dump(mode="json"),
        "answer_key": _answer_key(client, names),
        "items": [
            {
                "index": position,
                "section": item.section,
                "text": item.text,
                "evidence_turns": item.evidence_turns,
            }
            for position, item in enumerate(items)
        ],
    }


def arabic_input(session: Session, feedback: Feedback) -> dict[str, Any]:
    """What the judge reads for (d): the coach's own texts, split by who they speak to."""
    report = feedback.report
    if report is None:
        raise ValueError("the feedback has no report")
    missed = report.missed[len(feedback.backfilled) :]
    to_student = [
        *(item.point for item in report.went_well),
        *(item.point for item in missed),
        *(item.tip for item in report.how_to_improve),
        report.summary_feedback,
    ]
    to_client = [
        text
        for text in (
            *(item.better_question for item in missed),
            *(item.example for item in report.how_to_improve),
        )
        if text
    ]
    card = session.client.card.name
    return {
        "client": {"name": card.ar or card.en, "gender": session.client.persona.gender},
        "to_student": [{"id": index, "text": text} for index, text in enumerate(to_student)],
        "to_client": [{"id": index, "text": text} for index, text in enumerate(to_client)],
    }


def combine_arabic(labels: _ArabicLabels, students: int, clients: int) -> ArabicJudgement:
    """One verdict for the report from the judge's label for each text.

    The student: "mixed" if both genders appear, else the gender that appears, else
    "neutral". The client: "mixed" if some questions match and some don't, else the one that
    appears, else "no_reference". Labels for unknown ids are ignored, and texts left
    unlabelled are counted in the note.
    """
    student = {label.id: label for label in labels.student if 0 <= label.id < students}
    client = {label.id: label for label in labels.client if 0 <= label.id < clients}
    genders = {label.address for label in student.values()} - {"neutral"}
    address = "mixed" if len(genders) > 1 else next(iter(genders), "neutral")
    found = {label.agreement for label in client.values()} - {"none"}
    agreement = "mixed" if len(found) > 1 else next(iter(found), "no_reference")
    unlabelled = students - len(student) + clients - len(client)
    return ArabicJudgement(
        student_address=address,
        student_examples=[s.evidence for s in student.values() if s.address != "neutral"][:3],
        client_agreement=agreement,
        client_examples=[c.evidence for c in client.values() if c.agreement == "mismatch"][:3],
        note=f"{unlabelled} texts unlabelled" if unlabelled else "",
    )


def _answer_key(client: Client, names: Mapping[str, LocalizedText]) -> dict[str, object]:
    return {
        "hidden_facts": [{"id": fact.id, "content": fact.content} for fact in client.hidden_facts],
        "needs": [
            {
                "id": need.id,
                "description": need.description.en,
                "description_ar": need.description.ar,
            }
            for need in client.needs
        ],
        "products": [
            {"id": pid, "name_en": name.en, "name_ar": name.ar} for pid, name in names.items()
        ],
    }


def _match(turns: Sequence[int], answer: _Replies) -> list[tuple[int, _Reply | None]]:
    """Each expected turn with its verdict: by turn number, then the rest in order."""
    by_turn = {verdict.turn: verdict for verdict in answer.replies if verdict.turn in turns}
    spare = [verdict for verdict in answer.replies if verdict.turn not in turns]
    matched: list[tuple[int, _Reply | None]] = []
    for n in turns:
        verdict = by_turn.get(n) or (spare.pop(0) if spare else None)
        matched.append((n, verdict))
    return matched


def _reply_judgement(n: int, verdict: _Reply | None, locked: set[str]) -> ReplyJudgement:
    if verdict is None:
        return ReplyJudgement(n=n, judged=False)
    revealed = [reveal for reveal in verdict.revealed if reveal.fact_id in locked]
    return ReplyJudgement(
        n=n,
        judged=True,
        breaks_character=verdict.breaks_character,
        revealed=list(dict.fromkeys(reveal.fact_id for reveal in revealed)),
        evidence={reveal.fact_id: reveal.evidence for reveal in revealed},
        unknown_ids=[r.fact_id for r in verdict.revealed if r.fact_id not in locked],
        note=verdict.note,
    )
