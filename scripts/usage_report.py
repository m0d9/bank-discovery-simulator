"""A usage report for faculty, in Markdown, from the app's telemetry in `data/events.jsonl`.

    uv run --project backend python scripts/usage_report.py [--out report.md]

It reports how far sessions get, how often students find each client's hidden facts, how often
the gate fails and the client breaks character, each role's latency and tokens per session,
and an estimated cost when prices are configured.

It reads counts, flags, ids, models and timings only. Message text, which the events hold only
when `LOG_TRANSCRIPTS=true`, is never read, so it can't reach the report: each event is reduced
to those fields as soon as it is parsed, and a value that should be an id, a model name or a
prompt version but holds anything else (a space, a comma, an Arabic letter) is dropped.
"""

import argparse
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from pydantic import ValidationError

from app.config import Settings, get_settings
from app.content import Client, ContentRegistry, ContentValidationError, load_registry
from app.telemetry.events import EVENTS_FILE

REPO_ROOT = Path(__file__).resolve().parents[1]
ROLES = ("gate", "client", "coach")
NONE = "–"
# Ids, model names and prompt versions: a sentence can never match, so no message text gets
# into the report even through a field that should hold an id.
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,99}")


@dataclass
class SessionUsage:
    """What one session's events say about it."""

    client_id: str | None = None
    started: bool = False
    turns: int = 0
    unlocked: set[str] = field(default_factory=set)
    wrapped_up: bool = False
    feedback: bool = False
    used: set[tuple[str, str]] = field(default_factory=set)
    """(role, model) pairs the session called: the gate and the client in each turn, and the
    coach whenever it ran (a cached report doesn't count)."""


@dataclass(frozen=True)
class Call:
    """The measurements of one `llm_call` event."""

    role: str
    model: str
    prompt_version: str | None
    latency_ms: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    cost_usd: float | None


@dataclass(frozen=True)
class TurnFlags:
    """What went wrong in one student turn, if anything, and the models that served it."""

    gate_model: str | None
    client_model: str | None
    gate_failed: bool
    regenerated: bool
    role_break: bool


@dataclass
class Usage:
    """Everything the report needs from the events: numbers, flags and ids only."""

    events: int = 0
    unreadable: int = 0
    first: datetime | None = None
    last: datetime | None = None
    sessions: dict[str, SessionUsage] = field(default_factory=dict)
    calls: list[Call] = field(default_factory=list)
    unlabelled_calls: int = 0
    turns: list[TurnFlags] = field(default_factory=list)
    versions: set[tuple[str, str]] = field(default_factory=set)
    """(role, prompt version) pairs that the sessions' own events recorded."""

    def add(self, event: Mapping[str, Any]) -> None:
        """Take what the report needs from one event, and nothing else."""
        self.events += 1
        when = _timestamp(event.get("ts"))
        if when is not None:
            self.first = when if self.first is None else min(self.first, when)
            self.last = when if self.last is None else max(self.last, when)
        kind = event.get("event")
        if kind == "llm_call":
            self._call(event)
            return
        session_id = _label(event.get("session_id"))
        if session_id is None:
            return
        session = self.sessions.setdefault(session_id, SessionUsage())
        if session.client_id is None:
            session.client_id = _label(event.get("client_id"))
        if kind == "session_created":
            session.started = True
        elif kind == "turn":
            self._turn(session, event)
        elif kind == "wrapped_up":
            session.wrapped_up = True
            session.unlocked.update(_labels(event.get("unlocked")))
        elif kind == "feedback_generated":
            session.feedback = True
            version = _label(event.get("prompt_version"))
            if version is not None:
                self.versions.add(("coach", version))
            model = _label(event.get("model"))
            if model is not None and event.get("cached") is not True:
                session.used.add(("coach", model))

    def matched_calls(self) -> list[Call]:
        """The calls made for interviews.

        `llm_call` events carry no session id, so a call counts when its prompt version (before
        any `+` suffix, which the client adds when it regenerates a reply) is one that a turn or
        a feedback event recorded for the same role. The smoke check's calls and the evaluation
        judge's never match.
        """
        return [
            call
            for call in self.calls
            if call.prompt_version is not None
            and (call.role, call.prompt_version.split("+", 1)[0]) in self.versions
        ]

    def _call(self, event: Mapping[str, Any]) -> None:
        role, model = _label(event.get("role")), _label(event.get("model"))
        if role is None or model is None:
            self.unlabelled_calls += 1
            return
        self.calls.append(
            Call(
                role=role,
                model=model,
                prompt_version=_label(event.get("prompt_version")),
                latency_ms=_int(event.get("latency_ms")),
                prompt_tokens=_int(event.get("prompt_tokens")),
                completion_tokens=_int(event.get("completion_tokens")),
                cost_usd=_number(event.get("est_cost_usd")),
            )
        )

    def _turn(self, session: SessionUsage, event: Mapping[str, Any]) -> None:
        session.turns += 1
        session.unlocked.update(_labels(event.get("unlocked")))
        models = _mapping(event.get("models"))
        gate, client = _label(models.get("gate")), _label(models.get("client"))
        for role, model in (("gate", gate), ("client", client)):
            if model is not None:
                session.used.add((role, model))
        versions = _mapping(event.get("prompt_versions"))
        for role, key in (("gate", "gate"), ("client", "client_system")):
            version = _label(versions.get(key))
            if version is not None:
                self.versions.add((role, version))
        self.turns.append(
            TurnFlags(
                gate_model=gate,
                client_model=client,
                gate_failed=event.get("gate_failed") is True,
                regenerated=event.get("regenerated") is True,
                role_break=event.get("role_break") is True,
            )
        )


def read_usage(path: Path) -> Usage:
    """Read the events file. A line that isn't a JSON event is counted, never fatal."""
    usage = Usage()
    # A line cut short mid-character still decodes; json.loads then rejects it.
    with path.open(encoding="utf-8", errors="replace") as lines:
        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                usage.unreadable += 1
                continue
            if isinstance(event, dict) and isinstance(event.get("event"), str):
                usage.add(event)
            else:
                usage.unreadable += 1
    return usage


def render(usage: Usage, registry: ContentRegistry, source: str) -> str:
    """The whole report, as Markdown."""
    interviews = [session for session in usage.sessions.values() if session.turns]
    lines = [
        "# Usage report",
        "",
        f"From `{source}`: {_plural(usage.events, 'event')}{_period(usage)}.",
        "The report reads counts, ids, models and timings only, never message text.",
        "An *interview* below is a session with at least one student turn.",
        "",
    ]
    lines += _sessions(usage)
    lines += _discovery(interviews, registry)
    lines += _per_turn(usage.turns)
    matched = usage.matched_calls()
    lines += _latency(matched)
    lines += _tokens(matched, usage.sessions.values())
    lines += _cost(matched, len(interviews))
    lines += _method(usage, matched)
    return "\n".join(lines).rstrip("\n") + "\n"


def _sessions(usage: Usage) -> list[str]:
    sessions = list(usage.sessions.values())
    started = sum(session.started for session in sessions)
    stages = [
        ("Interviewed", [session for session in sessions if session.turns]),
        ("Reached wrap-up", [session for session in sessions if session.wrapped_up]),
        ("Reached feedback", [session for session in sessions if session.feedback]),
    ]
    rows = [["Started", _n(started), _share(started, started), NONE]]
    for name, members in stages:
        turns = [session.turns for session in members]
        rows.append([name, _n(len(members)), _share(len(members), started), _median(turns)])
    header = ["Stage", "Sessions", "Share of started", "Median student turns"]
    return ["## Sessions", "", *_table(header, "lrrr", rows), ""]


def _discovery(interviews: Sequence[SessionUsage], registry: ContentRegistry) -> list[str]:
    lines = [
        "## How often students find each hidden fact",
        "",
        "The share of interviews in which the fact was unlocked, by a question or by a product"
        " pitch.",
        "",
    ]
    by_client: dict[str, list[SessionUsage]] = defaultdict(list)
    for session in interviews:
        if session.client_id is not None:
            by_client[session.client_id].append(session)
    if not by_client:
        lines += ["No interviews yet.", ""]
    clients = registry.list_clients()
    known = {client.id for client in clients}
    for client in clients:
        if client.id in by_client:
            lines += _client_facts(client.id, client, by_client[client.id])
    for client_id in sorted(set(by_client) - known):
        lines += _client_facts(client_id, None, by_client[client_id])
    idle = [_code(client.id) for client in clients if client.id not in by_client]
    if by_client and idle:
        lines += [f"No interviews yet with {', '.join(idle)}.", ""]
    return lines


def _client_facts(
    client_id: str, client: Client | None, sessions: Sequence[SessionUsage]
) -> list[str]:
    if client is None:
        heading = f"### `{client_id}` (no longer in the content)"
        facts: list[tuple[str, str]] = []
    else:
        heading = f"### {client.card.name.en} (`{client_id}`)"
        facts = [(fact.id, fact.importance) for fact in client.hidden_facts]
    listed = {fact_id for fact_id, _ in facts}
    found = {fact_id for session in sessions for fact_id in session.unlocked}
    gone = NONE if client is None else "no longer in the content"
    facts += [(fact_id, gone) for fact_id in sorted(found - listed)]
    total = len(sessions)
    wrapped = sum(session.wrapped_up for session in sessions)
    rows = [
        [_code(fact_id), importance, _of(sum(fact_id in s.unlocked for s in sessions), total)]
        for fact_id, importance in facts
    ]
    summary = f"{_plural(total, 'interview')}, {_n(wrapped)} wrapped up."
    table = _table(["Hidden fact", "Importance", "Found in"], "llr", rows) if rows else []
    return [heading, "", summary, "", *table, *([""] if table else [])]


def _per_turn(turns: Sequence[TurnFlags]) -> list[str]:
    lines = ["## Gate failures and character breaks", ""]
    if not turns:
        return [*lines, "No student turns yet.", ""]
    gate: dict[str, list[TurnFlags]] = defaultdict(list)
    client: dict[str, list[TurnFlags]] = defaultdict(list)
    for turn in turns:
        if turn.gate_model is not None:
            gate[turn.gate_model].append(turn)
        if turn.client_model is not None:
            client[turn.client_model].append(turn)
    gate_rows = [
        [_code(model), _n(len(group)), _rate(sum(t.gate_failed for t in group), len(group))]
        for model, group in _by_size(gate)
    ]
    client_rows = [
        [
            _code(model),
            _n(len(group)),
            _rate(sum(t.regenerated for t in group), len(group)),
            _rate(sum(t.role_break for t in group), len(group)),
        ]
        for model, group in _by_size(client)
    ]
    return [
        *lines,
        "A gate failure is a turn whose gate call failed, so it unlocked nothing.",
        "",
        *_table(["Gate model", "Turns", "Gate failures"], "lrr", gate_rows),
        "",
        "A character break is a client reply that spoke of itself as an AI, a model or a"
        " prompt, so it was regenerated. The fallback line is the fixed line shown when the"
        " regenerated reply broke character too.",
        "",
        *_table(
            ["Client model", "Turns", "Character breaks", "Fallback line"], "lrrr", client_rows
        ),
        "",
    ]


def _latency(matched: Sequence[Call]) -> list[str]:
    lines = ["## Latency per call", ""]
    groups = _groups(matched)
    if not groups:
        return [*lines, "No model calls for interviews yet.", ""]
    rows = []
    for (role, model), calls in groups:
        latencies = [call.latency_ms for call in calls if call.latency_ms is not None]
        rows.append(
            [
                role,
                _code(model),
                _n(len(calls)),
                _seconds(nearest_rank(latencies, 0.5)),
                _seconds(nearest_rank(latencies, 0.95)),
            ]
        )
    return [*lines, *_table(["Role", "Model", "Calls", "p50", "p95"], "llrrr", rows), ""]


def _tokens(matched: Sequence[Call], sessions: Iterable[SessionUsage]) -> list[str]:
    lines = ["## Tokens per session", ""]
    groups = _groups(matched)
    if not groups:
        return [*lines, "No model calls for interviews yet.", ""]
    users = Counter(pair for session in sessions for pair in session.used)
    rows = []
    for (role, model), calls in groups:
        count = users[(role, model)]
        prompt = sum(call.prompt_tokens or 0 for call in calls)
        completion = sum(call.completion_tokens or 0 for call in calls)
        reported = any(
            call.prompt_tokens is not None or call.completion_tokens is not None for call in calls
        )
        if count and reported:
            # The total adds the rounded columns, so the row adds up as printed.
            per_prompt, per_completion = round(prompt / count), round(completion / count)
            cells = [_n(per_prompt), _n(per_completion), _n(per_prompt + per_completion)]
        else:
            cells = [NONE, NONE, NONE]
        rows.append([role, _code(model), _n(count), *cells])
    header = ["Role", "Model", "Sessions", "Input", "Output", "Total"]
    return [*lines, *_table(header, "llrrrr", rows), ""]


def _cost(matched: Sequence[Call], interviews: int) -> list[str]:
    lines = ["## Estimated cost", ""]
    costs = [call.cost_usd for call in matched if call.cost_usd is not None]
    if not costs:
        return [
            *lines,
            "No estimate: no call recorded a cost, because no prices were configured when the"
            " calls ran. Set `LLM_PRICE_INPUT_PER_MTOK` and `LLM_PRICE_OUTPUT_PER_MTOK` (USD per"
            " million tokens) in `.env` to record one.",
            "",
        ]
    total = sum(costs)
    per = f", or {_usd(total / interviews)} per interview" if interviews else ""
    return [
        *lines,
        f"{_usd(total)} in total{per}. {_n(len(costs))} of {_plural(len(matched), 'call')}"
        " recorded a cost, with the prices configured when each one ran.",
        "",
    ]


def _method(usage: Usage, matched: Sequence[Call]) -> list[str]:
    unmatched = len(usage.calls) - len(matched) + usage.unlabelled_calls
    return [
        "## How this is counted",
        "",
        "- `llm_call` events carry no session id, so a model call counts for interviews when its"
        " prompt version is one that a turn or feedback event recorded for the same role. The"
        " calls that don't match, such as the smoke check's, are left out of latency, tokens"
        f" and cost: {_plural(unmatched, 'call')}.",
        "- Latency is by nearest rank, over every call: retries, regenerated replies and model"
        " swaps included.",
        "- Tokens per session: a role's tokens with that model, divided by the sessions that"
        " used the model for that role. A session counts for the coach when the coach ran, not"
        " when it reused a cached report.",
        f"- {_plural(usage.unreadable, 'line')} of the events file couldn't be read.",
    ]


def nearest_rank(values: Sequence[int], q: float) -> int | None:
    """The q-th quantile by nearest rank (q in 0..1), or None for no values; the same method
    as the evaluation (`evals/metrics.py`), so the two compare."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def _groups(calls: Iterable[Call]) -> list[tuple[tuple[str, str], list[Call]]]:
    """Calls by (role, model): gate, client, coach, then the most used model first."""
    groups: dict[tuple[str, str], list[Call]] = defaultdict(list)
    for call in calls:
        groups[(call.role, call.model)].append(call)

    def order(item: tuple[tuple[str, str], list[Call]]) -> tuple[int, int, str]:
        (role, model), group = item
        rank = ROLES.index(role) if role in ROLES else len(ROLES)
        return rank, -len(group), model

    return sorted(groups.items(), key=order)


def _by_size(groups: Mapping[str, list[TurnFlags]]) -> list[tuple[str, list[TurnFlags]]]:
    return sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))


def _table(header: Sequence[str], align: str, rows: Iterable[Sequence[str]]) -> list[str]:
    """A Markdown table; `align` holds one `l` or `r` per column."""
    rule = ["---:" if side == "r" else "---" for side in align]
    return [_row(header), _row(rule), *(_row(row) for row in rows)]


def _row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _period(usage: Usage) -> str:
    if usage.first is None or usage.last is None:
        return ""
    first, last = usage.first.date().isoformat(), usage.last.date().isoformat()
    return f" on {first} (UTC)" if first == last else f" from {first} to {last} (UTC)"


def _n(value: int) -> str:
    return f"{value:,}"


def _plural(count: int, noun: str) -> str:
    return f"{_n(count)} {noun}{'' if count == 1 else 's'}"


def _share(part: int, whole: int, digits: int = 0) -> str:
    return f"{part / whole:.{digits}%}" if whole else NONE


def _of(part: int, whole: int) -> str:
    return f"{_n(part)} of {_n(whole)} ({_share(part, whole)})"


def _rate(part: int, whole: int) -> str:
    return f"{_n(part)} ({_share(part, whole, 1)})"


def _median(values: Sequence[int]) -> str:
    if not values:
        return NONE
    middle = float(statistics.median(values))
    return _n(int(middle)) if middle.is_integer() else f"{middle:.1f}"


def _seconds(ms: int | None) -> str:
    return NONE if ms is None else f"{ms / 1000:.1f} s"


def _usd(amount: float) -> str:
    return f"${amount:,.4f}"


def _code(label: str) -> str:
    return f"`{label}`"


def _label(value: object) -> str | None:
    return value if isinstance(value, str) and _LABEL.fullmatch(value) else None


def _labels(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [label for label in map(_label, value) if label is not None]


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        return None
    return when.replace(tzinfo=UTC) if when.tzinfo is None else when.astimezone(UTC)


def _display(path: Path) -> str:
    """The path from the repository root when it's inside it, so the report names no home
    folder."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scripts/usage_report.py",
        description="Write a Markdown usage report from data/events.jsonl.",
    )
    parser.add_argument("--out", type=Path, help="write the report to this file, not stdout")
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
    out: TextIO = sys.stdout,
) -> int:
    """Parse the arguments, write the report and return the exit code."""
    args = parse_args(argv)
    if settings is None:
        try:
            settings = get_settings()
        except ValidationError as exc:
            # Name the settings only: their values may include the API key.
            names = ", ".join(sorted({str(error["loc"][0]) for error in exc.errors()}))
            hint = f"Settings are missing or invalid ({names}). Copy .env.example to .env."
            _say(sys.stderr, hint)
            return 2
    events = settings.DATA_DIR / EVENTS_FILE
    if not events.is_file():
        _say(sys.stderr, f"No events yet: {_display(events)} doesn't exist.")
        return 1
    try:
        registry = load_registry(settings.CONTENT_DIR)
    except ContentValidationError as exc:
        for message in exc.messages:
            _say(sys.stderr, message)
        return 1
    report = render(read_usage(events), registry, _display(events))
    if args.out is None:
        out.write(report)
        out.flush()
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    _say(out, f"wrote {_display(args.out)}")
    return 0


def _say(stream: TextIO, line: str) -> None:
    # Console output of a CLI, not logging.
    stream.write(line + "\n")
    stream.flush()


if __name__ == "__main__":
    sys.exit(main())
