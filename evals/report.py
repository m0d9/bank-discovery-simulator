"""Write the generated part of `docs/evaluation.md` from the committed results.

    uv run --project backend python -m evals.report

For each setup in `evals/configs.yaml`, it uses the latest complete run (every client and
every script) made with the current prompts; failing that, the latest complete run, labelled
as a baseline run with the older prompts it used. Only the text between the EVAL markers is
replaced.
"""

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

import yaml
from pydantic import BaseModel, ValidationError

from app.prompts import PROMPT_VERSION
from evals.configs import EVALS_DIR, REPO_ROOT, RESULTS_DIR, EvalConfigs, load_configs
from evals.metrics import ClaimStats, Latency, Metrics, Ratio
from evals.records import RunSummary

DOC = REPO_ROOT / "docs" / "evaluation.md"
NOTES_FILE = EVALS_DIR / "notes.yaml"
START = "<!-- EVAL:START -->"
END = "<!-- EVAL:END -->"
APP_PROMPTS = ("gate", "client_system", "client_reminder", "client_language", "coach")
NEW_DOC = f"""# Evaluation

How well the simulator's models do their jobs, measured with scripted interviews: whether the
client keeps its secrets, whether the gate unlocks the right facts, and whether the coach's
feedback is right. `make eval` runs every setup and regenerates the section below.

{START}
{END}
"""

Notes = Mapping[str, Mapping[str, "Note"]]


class Note(BaseModel):
    """An explanation for a counted unlock, shown only when the gate quoted `quote`."""

    quote: str
    note: str


class Chosen:
    """The run shown for one setup, and whether it used the current prompts."""

    def __init__(self, summary: RunSummary, current: bool) -> None:
        self.summary = summary
        self.current = current
        self.metrics = Metrics.model_validate(summary.metrics)


def load_summaries(results_dir: Path = RESULTS_DIR) -> list[RunSummary]:
    """Every results file, oldest first. Files that don't parse are skipped."""
    summaries = []
    for path in sorted(results_dir.glob("*.json")):
        try:
            summaries.append(RunSummary.model_validate_json(path.read_text(encoding="utf-8")))
        except ValidationError:
            continue
    return sorted(summaries, key=lambda summary: summary.started_at)


def choose(summaries: Sequence[RunSummary], config: str) -> Chosen | None:
    """The latest complete run of `config` with the current prompts, else the latest complete
    run of it, else None."""
    complete = [s for s in summaries if s.config == config and s.complete]
    current = [s for s in complete if _current(s)]
    if current:
        return Chosen(current[-1], True)
    return Chosen(complete[-1], False) if complete else None


def load_notes(path: Path = NOTES_FILE) -> dict[str, dict[str, Note]]:
    """The explanations shown next to counted results, by client and fact."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    return {
        str(client): {str(fact): Note.model_validate(note) for fact, note in facts.items()}
        for client, facts in (data or {}).items()
    }


def render(configs: EvalConfigs, chosen: Mapping[str, Chosen], notes: Notes) -> str:
    """The generated section, without its markers."""
    names = [name for name in configs.configs if name in chosen]
    parts = [
        _method(configs, chosen, names),
        _table(chosen, names),
        _notes(chosen, names, notes),
        _recommendation(configs, chosen),
    ]
    return "\n\n".join(part for part in parts if part)


def write(section: str, doc: Path = DOC) -> None:
    """Put `section` between the markers, creating the document if it doesn't exist."""
    text = doc.read_text(encoding="utf-8") if doc.exists() else NEW_DOC
    start, end = text.find(START), text.find(END)
    if start < 0 or end < start:
        raise ValueError(f"{doc} needs the markers {START} and {END}, in that order")
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(f"{text[: start + len(START)]}\n{section}\n{text[end:]}", encoding="utf-8")


def main(
    results_dir: Path = RESULTS_DIR,
    doc: Path = DOC,
    configs: EvalConfigs | None = None,
    out: TextIO = sys.stdout,
) -> int:
    """Regenerate the section and say which runs it used."""
    configs = configs or load_configs()
    summaries = load_summaries(results_dir)
    chosen = {
        name: found for name in configs.configs if (found := choose(summaries, name)) is not None
    }
    write(render(configs, chosen, load_notes()), doc)
    for name, found in chosen.items():
        marker = "" if found.current else f" ({_label(found.summary)})"
        out.write(f"{name}: {found.summary.config}-{found.summary.stamp}{marker}\n")
    missing = [name for name in configs.configs if name not in chosen]
    if missing:
        out.write(f"No complete run yet: {', '.join(missing)}\n")
    return 0


def _current(summary: RunSummary) -> bool:
    return not _older(summary)


def _older(summary: RunSummary) -> list[str]:
    """The app's prompts that the run used in an older version than the current one."""
    return [
        name for name in APP_PROMPTS if summary.prompt_versions.get(name) != PROMPT_VERSION[name]
    ]


def _label(summary: RunSummary) -> str:
    """How a run with older prompts is labelled wherever it's shown, such as "baseline run,
    older coach prompt": it predates the current prompts, so it's what they were measured
    against. Empty for a run with the current prompts."""
    older = [name.replace("_", " ") for name in _older(summary)]
    if not older:
        return ""
    listed = older[0] if len(older) == 1 else f"{', '.join(older[:-1])} and {older[-1]}"
    return f"baseline run, older {listed} prompt{'' if len(older) == 1 else 's'}"


def _method(configs: EvalConfigs, chosen: Mapping[str, Chosen], names: Sequence[str]) -> str:
    judge = configs.judge.model
    lines = [
        "### Method",
        "",
        "Each setup interviews the five golden clients once with each of four scripts, through"
        " the app's own `InterviewService` and coach (`evals/scenarios.py`):",
        "",
        "- **strong:** a generic opener, then each hidden fact's first example question in"
        " dependency order, then a pitch of a suitable product. Each fact should unlock at its"
        " own question, or one student turn earlier. The wrap-up lists every need.",
        "- **weak:** four generic lines, a pitch of an unsuitable product, then «So would that"
        " work for you?». Nothing should unlock except the facts that react to that product, at"
        " the pitch. The wrap-up is vague and recommends the pitched product.",
        "- **arabic-weak:** the weak script in Arabic, with the coach in Arabic.",
        "- **adversarial:** five attacks, one in Arabic. Nothing should unlock or be revealed.",
        "",
        f"**The judge** is `{judge}` for every setup, so its verdicts compare across setups. It"
        " decides whether adversarial replies break character or reveal a locked fact, whether"
        " each point of the coach's feedback is supported by the transcript, the summary and the"
        " analysis, and how Arabic feedback addresses the student and the client. The judge is a"
        " model and can be wrong."
        + (
            f" It is also strong-coach's coach model (`{judge}`), so that row's coach is judged by"
            " its own model, which is biased in its favour; the other rows are not."
            if any(configs.configs[name].coach == judge for name in names)
            else ""
        ),
        "",
        "**Each setup ran once,** so every number is one sample: a single flip in a five-report"
        " row moves its rate by 20 points.",
        "",
        "| Setup | Run | Coach prompt | Notes |",
        "|---|---|---|---|",
    ]
    for name in names:
        found = chosen[name]
        summary = found.summary
        notes = []
        if summary.replay_of:
            notes.append(f"coach and judge replayed on `{summary.replay_of}`'s interviews")
        if not found.current:
            notes.append(f"**{_label(summary)}**")
        lines.append(
            f"| `{name}` | `{summary.config}-{summary.stamp}`"
            f" | `{summary.prompt_versions.get('coach', '?')}` | {'; '.join(notes) or '-'} |"
        )
    return "\n".join(lines)


def _table(chosen: Mapping[str, Chosen], names: Sequence[str]) -> str:
    def row(label: str, cells: Sequence[str]) -> str:
        return f"| {label} | {' | '.join(cells)} |"

    m = {name: chosen[name].metrics for name in names}
    s = {name: chosen[name].summary for name in names}
    rows = [
        "### Comparison",
        "",
        row("", [_heading(name, chosen[name]) for name in names]),
        "|---" * (len(names) + 1) + "|",
        row("Models: gate · client · coach", [_models(s[n].models) for n in names]),
        row("**Gate** precision (all scripts)", [_pct(m[n].gate.unlocks) for n in names]),
        row("Gate recall (strong)", [_pct(m[n].gate.recall) for n in names]),
        row(
            "False unlocks: weak · arabic-weak · strong · adversarial",
            [
                _counts(m[n].gate.false_by_script, ("weak", "arabic-weak", "strong", "adversarial"))
                for n in names
            ],
        ),
        row(
            "**Extraction successes** (target 0)",
            [_of(m[n].gate.extraction, m[n].gate.extraction_unjudged) for n in names],
        ),
        row(
            "Gate call failures · rejected quotes",
            [f"{m[n].gate.gate_failed} · {m[n].gate.gate_rejected}" for n in names],
        ),
        row(
            "**Client** character breaks: judge (adversarial) · pattern (all)",
            [
                f"{_of(m[n].client.judge_breaks, m[n].client.adversarial_unjudged)}"
                f" · {m[n].client.pattern_breaks}"
                for n in names
            ],
        ),
        row(
            "Regenerated replies · fallback lines",
            [
                f"{m[n].client.regenerated}"
                f" · {m[n].client.fallback.num} of {m[n].client.fallback.den}"
                for n in names
            ],
        ),
        row(
            "Language mismatches: retried · fixed",
            [
                f"{m[n].client.language_mismatch}: {m[n].client.language_retried}"
                f" · {m[n].client.language_fixed}"
                for n in names
            ],
        ),
        row(
            "**Coach** schema-valid on the first attempt",
            [_pct(m[n].coach.schema_valid_first) for n in names],
        ),
        row(
            "Degraded · JSON retried · backfilled entries",
            [
                f"{m[n].coach.degraded} · {m[n].coach.json_retried} · {m[n].coach.backfilled}"
                for n in names
            ],
        ),
        row(
            "Missed-critical recall before backfill (weak, arabic-weak)",
            [_pct(m[n].coach.missed_critical) for n in names],
        ),
        row(
            "Unsuitable product flagged (weak, arabic-weak)",
            [_pct(m[n].coach.unsuitable_flagged) for n in names],
        ),
        row(
            "Strong: praise given and grounded",
            [_pct(m[n].coach.strong_praise_valid) for n in names],
        ),
        row(
            "**Coach false-claim rate** (judged items)",
            [_claims(m[n].coach.claims.get("all")) for n in names],
        ),
    ]
    for script in ("strong", "weak", "arabic-weak"):
        rows.append(row(f"… {script}", [_claims(m[n].coach.claims.get(script)) for n in names]))
    rows += [
        row(
            "Unsupported, by category",
            [_dict(_categories(m[n].coach.claims.get("all"))) for n in names],
        ),
        row(
            "Guards: items dropped, by reason", [_dict(m[n].coach.dropped_by_reason) for n in names]
        ),
        row("Guards: fields cleared", [_dict(m[n].coach.cleared) for n in names]),
        row(
            "Guards: `mixed_script` fields (reports) · `needs_after_pitch`",
            [
                f"{m[n].coach.mixed_script} ({m[n].coach.mixed_script_reports})"
                f" · {m[n].coach.needs_after_pitch}"
                for n in names
            ],
        ),
        row(
            "**Arabic** reports: student address",
            [_dict(m[n].coach.arabic_address, m[n].coach.arabic_unjudged) for n in names],
        ),
        row(
            "Arabic reports: client gender agreement",
            [_dict(m[n].coach.arabic_agreement, m[n].coach.arabic_unjudged) for n in names],
        ),
        row(
            "Arabic reports: `mixed_script` fields",
            [str(m[n].coach.arabic_mixed_script) for n in names],
        ),
        row(
            "**Latency**, warm p50 / p95: gate",
            [_latency(m[n].perf.warm.get("gate")) for n in names],
        ),
        row("… client", [_latency(m[n].perf.warm.get("client")) for n in names]),
        row("… coach, every call (swaps included)", [_latency(m[n].perf.coach_all) for n in names]),
        row(
            "Tokens per session: gate · client · coach",
            [
                " · ".join(
                    f"{m[n].perf.tokens_per_session.get(role, 0):,.0f}"
                    for role in ("gate", "client", "coach")
                )
                for n in names
            ],
        ),
        row(
            "Coach completion tokens, p50 / p95",
            [_tokens(m[n].perf.coach_completion_tokens) for n in names],
        ),
        row(
            "Run time (of which the judge)",
            [
                f"{s[n].duration_s / 60:.0f} min ({m[n].perf.judge_seconds / 60:.0f} min)"
                for n in names
            ],
        ),
    ]
    return "\n".join(rows)


def _notes(chosen: Mapping[str, Chosen], names: Sequence[str], notes: Notes) -> str:
    clients = list(dict.fromkeys(c for name in names for c in chosen[name].summary.clients))
    lines = ["### Notes by client"]
    for client in clients:
        bullets: list[str] = []
        for name in names:
            bullets += [f"`{name}` · {text}" for text in _client_notes(chosen[name], client, notes)]
        lines += ["", f"**{client}**", ""]
        lines += [f"- {bullet}" for bullet in bullets] or ["- No failures in any setup."]
    return "\n".join(lines)


def _client_notes(found: Chosen, client: str, notes: Notes) -> list[str]:
    gate, coach, client_m = found.metrics.gate, found.metrics.coach, found.metrics.client
    out: list[str] = []
    for unlock in (u for u in gate.false_unlocks if u.client_id == client):
        how = "by the pitch rule" if unlock.by_pitch else f"quoting «{unlock.quote}»"
        text = (
            f"{unlock.script}: false unlock of `{unlock.fact_id}` at turn {unlock.n}"
            f" («{unlock.student}»), {how}."
        )
        # An attack's unlock is an extraction: an explanation never goes next to it.
        note = notes.get(client, {}).get(unlock.fact_id)
        explained = (
            note is not None and unlock.script != "adversarial" and unlock.quote == note.quote
        )
        out.append(f"{text} *{note.note.strip()}*" if note is not None and explained else text)
    for miss in (m for m in gate.misses if m.client_id == client):
        where = f"unlocked at turn {miss.unlocked_at}" if miss.unlocked_at else "never unlocked"
        out.append(
            f"strong: `{miss.fact_id}` didn't unlock at its question («{miss.probe}»): {where}."
        )
    for extraction in (e for e in gate.extractions if e.client_id == client):
        what = ", ".join(f"`{f}`" for f in [*extraction.unlocked, *extraction.revealed])
        out.append(
            f"adversarial: extraction at turn {extraction.n} («{extraction.attack}»): {what}."
        )
    for item in (b for b in client_m.breaks if b.key.startswith(f"{client}--")):
        out.append(
            f"{item.key.split('--')[1]}: character break at turn {item.n}"
            f" ({item.by}). {item.note}".strip()
        )
    for session in (r for r in found.summary.sessions if r.client_id == client):
        outcome = session.coach
        if session.error:
            out.append(f"{session.script}: {session.error}.")
        if outcome is None:
            continue
        if outcome.degraded:
            out.append(
                f"{session.script}: the coach failed ({outcome.error}); the feedback was degraded."
            )
        if outcome.backfilled:
            out.append(
                f"{session.script}: the coach left out"
                f" {', '.join(f'`{n}`' for n in outcome.backfilled)}; code backfilled it."
            )
        if (
            session.script in ("weak", "arabic-weak")
            and outcome.report is not None
            and session.pitched
        ):
            flagged = {item.get("product_id") for item in outcome.report.get("missed", [])}
            if session.pitched not in flagged:
                out.append(
                    f"{session.script}: the unsuitable `{session.pitched}` has no `missed` item."
                )
    for claim in (c for c in coach.unsupported if c.client_id == client):
        out.append(
            f"{claim.script}: unsupported ({claim.category}) {claim.section}:"
            f" «{_short(claim.text)}»"
        )
    return out


def _recommendation(configs: EvalConfigs, chosen: Mapping[str, Chosen]) -> str:
    name = configs.recommended
    found = chosen.get(name)
    if found is None:
        return f"**Recommendation:** `{name}` (no complete run yet)."
    m = found.metrics
    return (
        f"**Recommendation:** `{name}`: gate precision {_pct(m.gate.unlocks)}, recall"
        f" {_pct(m.gate.recall)}, {m.gate.extraction.num} extraction successes, coach false"
        f" claims {_claims(m.coach.claims.get('all'))},"
        f" coach p95 {_seconds(m.perf.coach_all.p95_ms)}."
    )


def _heading(name: str, found: Chosen) -> str:
    return f"`{name}`" if found.current else f"`{name}` ({_label(found.summary)})"


def _models(models: Mapping[str, str]) -> str:
    return " · ".join(f"`{models.get(role, '?')}`" for role in ("gate", "client", "coach"))


def _pct(ratio: Ratio) -> str:
    if not ratio.den:
        return "–"
    return f"{ratio.num}/{ratio.den} ({100 * ratio.num / ratio.den:.0f}%)"


def _of(ratio: Ratio, unjudged: int = 0) -> str:
    text = f"{ratio.num} of {ratio.den}"
    return f"{text} ({unjudged} unjudged)" if unjudged else text


def _claims(stats: ClaimStats | None) -> str:
    if stats is None or not stats.judged:
        return "–"
    text = f"{stats.unsupported}/{stats.judged} ({100 * stats.unsupported / stats.judged:.0f}%)"
    return f"{text}, {stats.unjudged} unjudged" if stats.unjudged else text


def _categories(stats: ClaimStats | None) -> dict[str, int]:
    return dict(stats.categories) if stats is not None else {}


def _counts(counts: Mapping[str, int], keys: Sequence[str]) -> str:
    return " · ".join(str(counts.get(key, 0)) for key in keys)


def _dict(counts: Mapping[str, int], unjudged: int = 0) -> str:
    text = ", ".join(f"{key} {value}" for key, value in sorted(counts.items())) or "none"
    return f"{text}; {unjudged} unjudged" if unjudged else text


def _latency(latency: Latency | None) -> str:
    if latency is None or latency.p50_ms is None:
        return "–"
    return f"{_seconds(latency.p50_ms)} / {_seconds(latency.p95_ms)} (n={latency.calls})"


def _seconds(ms: int | None) -> str:
    return "–" if ms is None else f"{ms / 1000:.1f} s"


def _tokens(latency: Latency) -> str:
    if latency.p50_ms is None:
        return "–"
    return f"{latency.p50_ms:,} / {latency.p95_ms:,}"


def _short(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


if __name__ == "__main__":
    sys.exit(main())
