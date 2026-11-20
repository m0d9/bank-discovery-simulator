"""The Markdown export of a session (`GET /api/sessions/{id}/export?format=md`).

Before feedback exists, the export holds the transcript and the wrap-up only. Once the session
is `feedback_ready`, it adds the discovery map, the product verdicts, the coach's feedback and
the revealed client profile, in the language of the latest feedback. The labels come from
`export_labels.json`, in English and Arabic.
"""

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

from app.coaching.analysis import NeedResult, ProductVerdict
from app.coaching.coach import localized
from app.coaching.feedback import Feedback
from app.coaching.report import CoachReport
from app.content import LocalizedText
from app.simulation import Language, Session

LABELS_FILE = Path(__file__).with_name("export_labels.json")


def _load_labels() -> Mapping[Language, Mapping[str, str]]:
    data = json.loads(LABELS_FILE.read_text(encoding="utf-8"))
    return MappingProxyType({"en": data["en"], "ar": data["ar"]})


LABELS = _load_labels()

# Markup characters in text that the student or a model wrote: escaped, so the text stays
# text (no raw HTML, no accidental emphasis or table cells).
_SPECIAL = re.compile(r"([\\`*_\[\]<>|])")
_BLOCK_START = re.compile(r"^(\s*)([#>+=-])", re.MULTILINE)
_LIST_NUMBER = re.compile(r"^(\s*\d+)([.)])", re.MULTILINE)
# First Strong Isolate and Pop Directional Isolate.
_FSI, _PDI = "\u2068", "\u2069"


def export_filename(session: Session) -> str:
    """`interview-<client>-<yyyymmdd>.md`, dated by the session's start."""
    return f"interview-{session.client_id}-{session.created_at:%Y%m%d}.md"


def export_markdown(session: Session, feedback: Feedback | None) -> str:
    """The whole export as Markdown text. An Arabic export is wrapped in a right-to-left block."""
    return _Document(session, feedback).render()


class _Document:
    def __init__(self, session: Session, feedback: Feedback | None) -> None:
        self.session = session
        self.feedback = feedback
        self.language: Language = feedback.language if feedback else session.language
        self.labels = LABELS[self.language]
        self.lines: list[str] = []

    def render(self) -> str:
        self._header()
        self._transcript()
        if self.session.wrapup is not None:
            self._wrapup()
        if self.feedback is not None:
            self._discovery_map(self.feedback)
            self._verdicts(self.feedback)
            self._coach(self.feedback)
            self._revealed(self.feedback)
        self._paragraph("---")
        self._paragraph(self._free(self._text(self.session.bank.disclaimer)))
        body = "\n".join(self.lines).rstrip() + "\n"
        return f'<div dir="rtl">\n\n{body}\n</div>\n' if self.language == "ar" else body

    # --- sections ---------------------------------------------------------------------------

    def _header(self) -> None:
        session = self.session
        card = session.client.card
        name = self._text(card.name)
        headline = self._free(self._text(card.headline))
        models = session.models
        roles = [
            f"{self._label('role_client')} `{models.client}`",
            f"{self._label('role_gate')} `{models.gate}`",
            f"{self._label('role_coach')} `{models.coach}`",
        ]
        self._paragraph(f"# {self._free(self._label('title', name=name))}")
        self._list(
            [
                f"**{self._label('client')}:** {self._free(name)} – {headline}",
                f"**{self._label('date')}:** {session.created_at:%Y-%m-%d}",
                f"**{self._label('models')}:** " + " · ".join(roles),
            ]
        )

    def _transcript(self) -> None:
        client_name = self._text(self.session.client.card.name)
        self._paragraph(f"## {self._label('transcript')}")
        for turn in self.session.turns:
            speaker = self._label("you") if turn.role == "student" else client_name
            label = f"{self._label('turn', n=turn.n)} · {self._free(speaker)}"
            self._paragraph(f"**{label}:** {self._free(turn.text)}")

    def _wrapup(self) -> None:
        wrapup = self.session.wrapup
        if wrapup is None:
            return
        self._paragraph(f"## {self._label('wrapup')}")
        self._paragraph(f"### {self._label('your_summary')}")
        self._paragraph(
            "\n".join(f"> {line}" for line in self._free(wrapup.needs_summary).split("\n"))
        )
        self._paragraph(f"### {self._label('your_recommendations')}")
        self._list(
            f"**{self._free(self._product(item.product_id))}:** {self._free(item.reason)}"
            for item in wrapup.recommendations
        )

    def _discovery_map(self, feedback: Feedback) -> None:
        dash = "–"
        self._paragraph(f"## {self._label('discovery_map')}")
        header = [
            self._label(key) for key in ("col_need", "col_status", "col_turn", "col_question")
        ]
        rows = [
            "| " + " | ".join(header) + " |",
            "| --- | --- | --- | --- |",
        ]
        for need in feedback.analysis.needs:
            via = need.via
            cells = [
                self._need(need.need_id),
                self._label(f"status_{need.status}"),
                self._label("turn", n=via.turn) if via else dash,
                via.question if via else dash,
            ]
            rows.append("| " + " | ".join(self._cell(cell) for cell in cells) + " |")
        self._paragraph("\n".join(rows))

    def _verdicts(self, feedback: Feedback) -> None:
        analysis = feedback.analysis
        self._paragraph(f"## {self._label('verdicts')}")
        self._list(self._verdict(verdict) for verdict in analysis.products)
        if analysis.missed_opportunities:
            self._paragraph(f"### {self._label('missed_opportunities')}")
            self._list(
                f"**{self._free(self._product(item.product_id))}.** {self._label('fits')}: "
                + "; ".join(self._free(self._need(need_id)) for need_id in item.needs)
                for item in analysis.missed_opportunities
            )

    def _verdict(self, verdict: ProductVerdict) -> str:
        name = self._free(self._product(verdict.product_id))
        title = f"**{name}: {self._label(f'verdict_{verdict.verdict}')}.**"
        if verdict.verdict == "unsuitable":
            reasons = dict.fromkeys(self._text(reason.reason) for reason in verdict.reasons)
            line = f"{title} " + " ".join(self._free(reason) for reason in reasons)
            if verdict.ruled_out_at is not None:
                turn = self._label("turn", n=verdict.ruled_out_at)
                line += " " + self._label("ruled_out", turn=turn)
            return line
        if verdict.verdict == "suitable":
            needs = "; ".join(self._free(self._need(need_id)) for need_id in verdict.needs)
            return f"{title} {self._label('fits')}: {needs}"
        return f"{title} {self._label('not_in_key_note')}"

    def _coach(self, feedback: Feedback) -> None:
        self._paragraph(f"## {self._label('coach')}")
        report = feedback.report
        if report is None:
            self._paragraph(self._label("coach_unavailable"))
            return
        self._coach_sections(report)

    def _coach_sections(self, report: CoachReport) -> None:
        if report.went_well:
            self._paragraph(f"### {self._label('went_well')}")
            self._list(
                self._free(item.point) + self._evidence(item.evidence_turns)
                for item in report.went_well
            )
        if report.missed:
            self._paragraph(f"### {self._label('missed')}")
            items = []
            for missed in report.missed:
                item = self._free(missed.point) + self._evidence(missed.evidence_turns)
                if missed.better_question:
                    question = self._free(missed.better_question)
                    item += "  \n  " + self._label("better_question", question=question)
                items.append(item)
            self._list(items)
        if report.how_to_improve:
            self._paragraph(f"### {self._label('how_to_improve')}")
            items = []
            for tip in report.how_to_improve:
                item = self._free(tip.tip)
                if tip.example:
                    item += "  \n  " + self._label("example", example=self._free(tip.example))
                items.append(item)
            self._list(items)
        # As on the page, under the coach's sections: a model wrote them, the key did not.
        self._paragraph(f"*{self._label('coach_note')}*")
        self._paragraph(f"### {self._label('about_summary')}")
        self._paragraph(self._free(report.summary_feedback))

    def _revealed(self, feedback: Feedback) -> None:
        client = self.session.client
        persona = client.persona
        self._paragraph(f"## {self._label('revealed')}")
        self._paragraph(f"### {self._label('persona')}")
        fields: list[tuple[str, str | None]] = [
            ("age", str(persona.age)),
            ("occupation", persona.occupation),
            ("nationality", persona.nationality),
            ("family", persona.family),
            ("background", persona.background),
            ("personality", persona.personality),
            ("speaking_style", persona.speaking_style),
            ("financial_knowledge", self._label(f"knowledge_{persona.financial_knowledge}")),
        ]
        self._list(f"**{self._label(key)}:** {self._free(value)}" for key, value in fields if value)
        self._paragraph(f"### {self._label('open_facts')}")
        self._list(self._free(fact) for fact in client.open_facts)

        self._paragraph(f"### {self._label('hidden_facts')}")
        results = {fact.fact_id: fact for fact in feedback.analysis.facts}
        facts = []
        for fact in client.hidden_facts:
            result = results[fact.id]
            turn = result.unlocked_at_turn
            if turn is None:
                found = self._label("not_found")
            elif result.discovered_by == "product_pitch":
                found = self._label("found_by_pitch", n=turn)
            else:
                found = self._label("found_at", n=turn)
            importance = self._label(f"importance_{fact.importance}")
            facts.append(f"{self._free(fact.content)}  \n  {importance} · {found}")
        self._list(facts)

        self._paragraph(f"### {self._label('needs')}")
        statuses = {need.need_id: need for need in feedback.analysis.needs}
        for need in client.needs:
            self._need_entry(need.id, statuses[need.id])
        if client.referral_note is not None:
            self._paragraph(f"### {self._label('referral')}")
            self._paragraph(self._free(self._text(client.referral_note)))

    def _need_entry(self, need_id: str, result: NeedResult) -> None:
        need = next(need for need in self.session.client.needs if need.id == need_id)
        suitable = ", ".join(self._free(self._product(pid)) for pid in need.suitable_products)
        unsuitable = "; ".join(
            f"{self._free(self._product(entry.id))} ({self._free(self._text(entry.reason))})"
            for entry in need.unsuitable_products
        )
        status = self._label(f"status_{result.status}")
        none = self._label("none")
        self._list(
            [
                f"**{self._free(self._text(need.description))}** ({status})  \n"
                f"  {self._label('suitable_products')}: {suitable or none}  \n"
                f"  {self._label('unsuitable_products')}: {unsuitable or none}"
            ]
        )

    # --- helpers ----------------------------------------------------------------------------

    def _free(self, text: str) -> str:
        """Text that the student, a model or the content wrote, safe inside Markdown. In an
        Arabic export it is also isolated (FSI…PDI, the plain-text `dir="auto"`), so an English
        sentence keeps its own direction, full stop included, inside the right-to-left page."""
        safe = _inline(text)
        return f"{_FSI}{safe}{_PDI}" if self.language == "ar" and safe else safe

    def _cell(self, text: str) -> str:
        """Text for a table cell: one line."""
        return " ".join(self._free(text).split())

    def _label(self, key: str, **values: object) -> str:
        return self.labels[key].format(**values)

    def _text(self, text: LocalizedText) -> str:
        return localized(text, self.language)

    def _product(self, product_id: str) -> str:
        product = self.session.products.get(product_id)
        return self._text(product.name) if product is not None else product_id

    def _need(self, need_id: str) -> str:
        need = next((need for need in self.session.client.needs if need.id == need_id), None)
        return self._text(need.description) if need is not None else need_id

    def _evidence(self, turns: Sequence[int]) -> str:
        if not turns:
            return ""
        separator = "، " if self.language == "ar" else ", "
        return f" ({self._label('evidence')}: {separator.join(str(n) for n in turns)})"

    def _paragraph(self, text: str) -> None:
        self.lines.extend([text, ""])

    def _list(self, items: Iterable[str]) -> None:
        self._paragraph("\n".join(f"- {item}" for item in items))


def _inline(text: str) -> str:
    """Text that the student, a model or the content wrote, made safe inside Markdown, with
    its line breaks kept."""
    escaped = _SPECIAL.sub(r"\\\1", text.strip())
    escaped = _BLOCK_START.sub(r"\1\\\2", escaped)
    escaped = _LIST_NUMBER.sub(r"\1\\\2", escaped)
    return "  \n".join(line.rstrip() for line in escaped.splitlines())
