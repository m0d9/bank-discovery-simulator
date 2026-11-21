"""Run one model setup through the scripted interviews, then the judge, and save the results.

    uv run --project backend python -m evals.run --config default \
        [--clients all|id,id] [--scripts strong,weak,adversarial,arabic-weak] [--note TEXT]
    uv run --project backend python -m evals.run --replay evals/results/traces/<run> [--note TEXT]

Every session goes through `InterviewService` and `FeedbackService` in-process, the app's own
code path, with the setup's models. The judge runs once at the end, so Ollama swaps to it once.

`--replay` loads a run's recorded sessions and runs only the coach and the judge again: the
same interviews, so a prompt change can be compared on identical transcripts. Everything the
interviews measured (the gate, the client, the adversarial verdicts) is carried over.

Results go to `evals/results/<config>-<YYYYMMDD-HHMM>.json` (UTC), and the full traces to
`evals/results/traces/<config>-<stamp>/`, which git ignores.
"""

import argparse
import asyncio
import json
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO, get_args

from pydantic import ValidationError

from app.coaching import CoachCache, Feedback, FeedbackService, latest_feedback
from app.coaching.analysis import missed_critical_needs
from app.config import Settings
from app.content import ContentRegistry, ContentValidationError, UnknownProduct, load_registry
from app.llm import LLMClient, LLMError
from app.llm.client import OpenAICompatClient
from app.logging_setup import configure_logging
from app.prompts import PROMPT_VERSION
from app.simulation import (
    InterviewError,
    InterviewService,
    Language,
    Session,
    SessionStatus,
    SessionStore,
    TurnResult,
    breaks_character,
)
from app.telemetry.events import EventLogger
from evals.configs import (
    REPO_ROOT,
    RESULTS_DIR,
    EvalConfigs,
    JudgeConfig,
    ModelConfig,
    load_configs,
)
from evals.judge import JUDGE_PROMPT_VERSION, Judge
from evals.metrics import Metrics, compute
from evals.records import (
    SUMMARY_EXCLUDE,
    CoachRecord,
    EventRecord,
    JudgeRecord,
    LanguageRetryRecord,
    Phase,
    RunInfo,
    RunSummary,
    SessionRecord,
    TurnRecord,
)
from evals.scenarios import SCRIPTS, Scenario, ScriptName, build_all

TRACES = "traces"
EVENTS_FILE = "events.jsonl"
RUN_FILE = "run.json"
SESSIONS = "sessions"


class CapturedEvents(EventLogger):
    """The app's telemetry, written to the trace's `events.jsonl` and kept in memory. Each event
    is tagged with its session's key and the run's phase: `llm_call` carries no session id."""

    def __init__(self, path: Path, carried: Sequence[EventRecord] = ()) -> None:
        super().__init__(path)
        self.records: list[EventRecord] = list(carried)
        self.key: str | None = None
        self.phase: Phase = "setup"

    async def emit(self, event: str, **fields: object) -> None:
        """Keep the event, then append it to the trace with its tags."""
        self.records.append(
            EventRecord(event=event, key=self.key, phase=self.phase, fields=dict(fields))
        )
        await super().emit(event, eval_key=self.key, eval_phase=self.phase, **fields)

    def of(self, key: str, event: str) -> list[dict[str, Any]]:
        """The fields of every `event` of the session `key`."""
        return [
            record.fields for record in self.records if record.key == key and record.event == event
        ]


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="evals.run", description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", help="a setup in evals/configs.yaml")
    parser.add_argument("--clients", default="all", help="all, or client ids separated by commas")
    parser.add_argument("--scripts", default=",".join(SCRIPTS), help="scripts separated by commas")
    parser.add_argument("--replay", type=Path, help="a trace folder: re-run its coach and judge")
    parser.add_argument("--note", default="", help="a note stored with the results")
    args = parser.parse_args(argv)
    if (args.config is None) == (args.replay is None):
        parser.error("give either --config or --replay")
    return args


def with_overrides(settings: Settings, config: ModelConfig, data_dir: Path) -> Settings:
    """The app's settings with the setup's models and retries. Transcripts are logged: the
    students are scripted, and the traces stay local."""
    update: dict[str, object] = {
        "LLM_MODEL_GATE": config.gate,
        "LLM_MODEL_CLIENT": config.client,
        "LLM_MODEL_COACH": config.coach,
        "LOG_TRANSCRIPTS": True,
        "DATA_DIR": data_dir,
    }
    if config.max_retries is not None:
        update["LLM_MAX_RETRIES"] = config.max_retries
    return settings.model_copy(update=update)


def judge_settings(settings: Settings, judge: JudgeConfig) -> Settings:
    """Settings for the judge's own client: its model as the coach, and its retries."""
    return settings.model_copy(
        update={"LLM_MODEL_COACH": judge.model, "LLM_MAX_RETRIES": judge.max_retries}
    )


def turn_record(index: int, kind: str, result: TurnResult) -> TurnRecord:
    """What one student line did."""
    retry = result.language_retry
    return TurnRecord(
        line=index,
        kind=kind,
        student=result.student_turn.text,
        n=result.student_turn.n,
        client=result.client_turn.text,
        eligible=list(result.eligible),
        unlocked=list(result.unlocked_now),
        by_pitch=list(result.unlocked_by_pitch),
        products=list(result.products_mentioned),
        gate_failed=result.gate_failed,
        gate_rejected=list(result.gate_rejected),
        gate_quotes=dict(result.gate_quotes),
        gate_note=result.gate_note,
        role_break=result.role_break,
        regenerated=result.regenerated,
        pattern_break=breaks_character(result.client_turn.text),
        language_retry=(
            LanguageRetryRecord(
                reason=retry.reason,
                retried=retry.retried,
                fixed=retry.fixed,
                first_text=retry.first_text,
            )
            if retry is not None
            else None
        ),
        latency_ms=dict(result.latency_ms),
    )


def coach_record(
    session: Session, feedback: Feedback, events: CapturedEvents, key: str
) -> CoachRecord:
    """The feedback and what the guards did, from the session and its telemetry."""
    generated = events.of(key, "feedback_generated")
    last = generated[-1] if generated else {}
    reasons = Counter(str(drop.get("reason")) for drop in events.of(key, "coach_item_dropped"))
    return CoachRecord(
        language=feedback.language,
        model=session.models.coach,
        prompt_version=str(last.get("prompt_version", PROMPT_VERSION["coach"])),
        degraded=feedback.degraded,
        error=last.get("error"),
        json_retried=bool(last.get("json_retried", False)),
        backfilled=list(feedback.backfilled),
        dropped=dict(last.get("dropped", {})),
        dropped_reasons=dict(reasons),
        cleared=dict(last.get("cleared", {})),
        mixed_script=int(last.get("mixed_script", 0)),
        needs_after_pitch=int(last.get("needs_after_pitch", 0)),
        latency_ms=int(last.get("latency_ms", 0)),
        missed_critical=[
            need.id for need in missed_critical_needs(session.client, feedback.analysis)
        ],
        report=feedback.report.model_dump(mode="json") if feedback.report is not None else None,
        analysis=feedback.analysis.model_dump(mode="json"),
    )


def snapshot(session: Session) -> dict[str, Any]:
    """The session as the replay restores it: everything but the feedback."""
    return session.model_dump(mode="json", exclude={"feedback"})


def restore(data: dict[str, Any]) -> Session:
    """A recorded session, wrapped up again and without feedback."""
    session = Session.model_validate(data)
    session.status = SessionStatus.WRAPPED_UP
    session.feedback = None
    return session


class Runner:
    """Runs scenarios and the judge for one setup, printing as it goes."""

    def __init__(
        self,
        *,
        settings: Settings,
        llm: LLMClient,
        judge: Judge,
        events: CapturedEvents,
        content: ContentRegistry,
        out: TextIO,
    ) -> None:
        store = SessionStore.from_settings(settings)
        self.store = store
        self.events = events
        self.judge = judge
        self.out = out
        self.interviews = InterviewService(
            store=store, llm=llm, settings=settings, events=events, content=content
        )
        self.feedback = FeedbackService(
            store=store, llm=llm, settings=settings, events=events, cache=CoachCache()
        )

    async def interview(
        self, scenario: Scenario, index: int, total: int
    ) -> tuple[SessionRecord, Session | None]:
        """One scripted interview, its wrap-up and the coach."""
        record = SessionRecord(
            key=scenario.key,
            client_id=scenario.client_id,
            script=scenario.script,
            language=scenario.language,
            pitched=scenario.pitched,
            expected={fact: list(lines) for fact, lines in scenario.expected.items()},
            allowed={fact: list(lines) for fact, lines in scenario.allowed.items()},
        )
        self.events.key, self.events.phase = scenario.key, "interview"
        say(
            self.out,
            f"\n[{index}/{total}] {scenario.client_id} · {scenario.script} ({scenario.language})",
        )
        session = await self.interviews.create_session(scenario.client_id, scenario.language)
        record.session_id = session.id
        say(self.out, f"  t0  Client: {session.turns[0].text}")
        for line_index, line in enumerate(scenario.lines):
            try:
                result = await self.interviews.student_message(session.id, line.text)
            except (InterviewError, LLMError) as exc:
                record.turns.append(
                    TurnRecord(
                        line=line_index,
                        kind=line.kind,
                        student=line.text,
                        error=f"{exc.code}: {exc.detail}",
                    )
                )
                say(self.out, f"  --  Student: {line.text}\n      [{exc.code}] {exc.detail}")
                continue
            turn = turn_record(line_index, line.kind, result)
            record.turns.append(turn)
            self._print_turn(record, turn)
        if scenario.wrapup is not None and scenario.coach_language is not None:
            if not any(turn.n is not None for turn in record.turns):
                record.error = "no turn succeeded, so there is no wrap-up"
            else:
                try:
                    await self.interviews.wrap_up(session.id, scenario.wrapup)
                except (InterviewError, UnknownProduct) as exc:
                    record.error = f"wrap-up failed: {exc}"
                else:
                    session = await self.coach(record, session, scenario.coach_language)
        record.snapshot = snapshot(session)
        return record, session

    async def coach(self, record: SessionRecord, session: Session, language: Language) -> Session:
        """Run the coach on a wrapped-up session, and record its feedback."""
        self.events.key, self.events.phase = record.key, "coach"
        session, feedback = await self.feedback.feedback(session.id, language)
        record.coach = coach_record(session, feedback, self.events, record.key)
        self._print_coach(record.coach)
        return session

    async def judge_all(
        self, pairs: Sequence[tuple[SessionRecord, Session | None]], *, replies: bool
    ) -> None:
        """Every judge call of the run, one after another. `replies=False` keeps the recorded
        verdicts on adversarial replies (the replay)."""
        self.events.phase = "judge"
        say(self.out, f"\nJudge ({self.judge.model})")
        for record, session in pairs:
            if session is None:
                continue
            self.events.key = record.key
            if replies and record.script == "adversarial":
                verdicts, error = await self.judge.replies(session)
                record.judge.replies = verdicts
                _note_error(record, "replies", error)
            feedback = latest_feedback(session)
            if feedback is None or feedback.report is None:
                continue
            items, error = await self.judge.grounding(session, feedback)
            record.judge.items = items
            _note_error(record, "grounding", error)
            if feedback.language == "ar":
                arabic, error = await self.judge.arabic(session, feedback)
                record.judge.arabic = arabic
                _note_error(record, "arabic", error)
            self._print_judge(record)

    def _print_turn(self, record: SessionRecord, turn: TurnRecord) -> None:
        say(self.out, f"  t{turn.n}  Student: {turn.student}")
        say(self.out, f"  t{(turn.n or 0) + 1}  Client: {turn.client}")
        marks = []
        for fact_id in turn.unlocked:
            if turn.line in record.expected.get(fact_id, []):
                verdict = "expected"
            elif turn.line in record.allowed.get(fact_id, []):
                verdict = "allowed"
            else:
                verdict = "NOT EXPECTED"
            how = "pitch" if fact_id in turn.by_pitch else f'"{turn.gate_quotes.get(fact_id, "")}"'
            marks.append(f"{fact_id} ({verdict}; {how})")
        flags = [
            name
            for name, on in (
                ("gate failed", turn.gate_failed),
                ("regenerated", turn.regenerated),
                ("fallback line", turn.role_break),
                ("pattern break", turn.pattern_break),
            )
            if on
        ]
        if turn.language_retry is not None:
            retry = turn.language_retry
            flags.append(f"language {retry.reason}: retried {retry.retried}, fixed {retry.fixed}")
        if turn.gate_rejected:
            flags.append(f"rejected quotes: {', '.join(turn.gate_rejected)}")
        latency = turn.latency_ms
        say(
            self.out,
            f"      unlocked: {', '.join(marks) or '-'}"
            f" · products: {', '.join(turn.products) or '-'}"
            f" · gate {latency.get('gate', 0)} ms · client {latency.get('client', 0)} ms"
            + (f" · {'; '.join(flags)}" if flags else ""),
        )

    def _print_coach(self, coach: CoachRecord) -> None:
        state = "DEGRADED" if coach.degraded else "ok"
        say(
            self.out,
            f"  coach ({coach.language}, {coach.model}): {state} in {coach.latency_ms / 1000:.1f} s"
            f" · json retried {coach.json_retried} · backfilled {coach.backfilled or '-'}"
            f" · dropped {coach.dropped_reasons or '-'} · cleared {coach.cleared or '-'}"
            f" · mixed script {coach.mixed_script}",
        )
        report = coach.report or {}
        for item in report.get("went_well", []):
            say(self.out, f"    + {item['point']} (turns {item['evidence_turns']})")
        for item in report.get("missed", []):
            ids = f"need {item['need_id']}, product {item['product_id']}"
            say(self.out, f"    - {item['point']} ({ids}) · ask: {item['better_question']}")
        for item in report.get("how_to_improve", []):
            say(self.out, f"    > {item['tip']} · e.g. {item['example']}")
        if report:
            say(self.out, f"    = {report['summary_feedback']}")

    def _print_judge(self, record: SessionRecord) -> None:
        verdicts = record.judge
        unsupported = [item for item in verdicts.items if item.supported is False]
        unjudged = sum(item.supported is None for item in verdicts.items)
        line = f"  {record.key}: {len(verdicts.items)} items, {len(unsupported)} unsupported"
        if unjudged:
            line += f", {unjudged} unjudged"
        if verdicts.arabic is not None:
            line += (
                f" · Arabic: student {verdicts.arabic.student_address},"
                f" client {verdicts.arabic.client_agreement}"
            )
        if verdicts.errors:
            line += f" · errors: {', '.join(verdicts.errors)}"
        say(self.out, line)
        for item in unsupported:
            say(
                self.out,
                f"    ✗ [{item.category}] {item.section}: {item.text}\n      judge: {item.reason}",
            )


async def run(
    config_name: str,
    configs: EvalConfigs,
    *,
    settings: Settings,
    llm: LLMClient | None,
    judge_llm: LLMClient | None,
    clients: Sequence[str] | None,
    scripts: Sequence[ScriptName],
    note: str,
    results_dir: Path,
    out: TextIO,
) -> Path:
    """Run one setup and save its summary and traces. Returns the summary's path."""
    config = configs.configs[config_name]
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    stamp = _stamp(results_dir, config_name, started_at)
    trace_dir = results_dir / TRACES / f"{config_name}-{stamp}"
    settings = with_overrides(settings, config, trace_dir)
    events = CapturedEvents(trace_dir / EVENTS_FILE)
    llm, judge_llm = _clients(settings, configs.judge, events, llm, judge_llm)
    content = load_registry(settings.CONTENT_DIR)
    all_clients = [client.id for client in content.list_clients()]
    chosen = list(clients) if clients else all_clients
    scenarios = build_all(content, chosen, scripts)
    judge = Judge(judge_llm, configs.judge)
    runner = Runner(
        settings=settings, llm=llm, judge=judge, events=events, content=content, out=out
    )
    say(
        out,
        f"Config {config_name}: gate {config.gate} · client {config.client} · coach {config.coach}"
        f" · judge {configs.judge.model} · LLM_MAX_RETRIES {settings.LLM_MAX_RETRIES}",
    )
    say(out, f"Prompts: {dict(PROMPT_VERSION)} · judge prompts: {dict(JUDGE_PROMPT_VERSION)}")
    pairs: list[tuple[SessionRecord, Session | None]] = []
    for index, scenario in enumerate(scenarios, start=1):
        record, session = await runner.interview(scenario, index, len(scenarios))
        # Kept at once: a crash later in the run still leaves the finished sessions.
        _write_json(trace_dir / SESSIONS / f"{record.key}.json", record.model_dump(mode="json"))
        pairs.append((record, session))
    await runner.judge_all(pairs, replies=True)
    records = [record for record, _ in pairs]
    info = RunInfo(
        config=config_name,
        stamp=stamp,
        note=note,
        models={"gate": config.gate, "client": config.client, "coach": config.coach},
        judge=configs.judge.model_dump(),
        settings=_settings_used(settings),
        git=_git(),
        prompt_versions=dict(PROMPT_VERSION),
        judge_prompt_versions=dict(JUDGE_PROMPT_VERSION),
        clients=chosen,
        scripts=list(scripts),
        complete=chosen == all_clients and list(scripts) == list(SCRIPTS),
        started_at=started_at.isoformat(timespec="seconds"),
        duration_s=round(time.perf_counter() - started, 1),
    )
    return _save(info, records, events.records, results_dir, trace_dir, out)


async def replay(
    trace_dir: Path,
    configs: EvalConfigs,
    *,
    settings: Settings,
    llm: LLMClient | None,
    judge_llm: LLMClient | None,
    note: str,
    results_dir: Path,
    out: TextIO,
) -> Path:
    """Re-run the coach and the judge on a run's recorded sessions. Returns the new summary."""
    original = RunInfo.model_validate_json((trace_dir / RUN_FILE).read_text(encoding="utf-8"))
    config = configs.configs[original.config]
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    stamp = _stamp(results_dir, original.config, started_at)
    new_dir = results_dir / TRACES / f"{original.config}-{stamp}"
    settings = with_overrides(settings, config, new_dir)
    carried = [
        event
        for event in load_events(trace_dir / EVENTS_FILE)
        if event.phase in ("setup", "interview")
    ]
    events = CapturedEvents(new_dir / EVENTS_FILE, carried)
    _write_events(new_dir / EVENTS_FILE, carried)
    llm, judge_llm = _clients(settings, configs.judge, events, llm, judge_llm)
    content = load_registry(settings.CONTENT_DIR)
    runner = Runner(
        settings=settings,
        llm=llm,
        judge=Judge(judge_llm, configs.judge),
        events=events,
        content=content,
        out=out,
    )
    say(
        out,
        f"Replay of {original.config}-{original.stamp}: coach {config.coach}"
        f" · judge {configs.judge.model}",
    )
    say(out, f"Prompts: {dict(PROMPT_VERSION)} · judge prompts: {dict(JUDGE_PROMPT_VERSION)}")
    records = load_sessions(trace_dir, original)
    pairs: list[tuple[SessionRecord, Session | None]] = []
    for index, record in enumerate(records, start=1):
        if record.coach is None or record.snapshot is None:
            pairs.append((record, None))
            continue
        say(out, f"\n[{index}/{len(records)}] {record.key}")
        session = restore(record.snapshot)
        runner.store.create(session)
        record.judge = JudgeRecord()
        session = await runner.coach(record, session, record.coach.language)
        record.snapshot = snapshot(session)
        pairs.append((record, session))
    await runner.judge_all(pairs, replies=False)
    info = original.model_copy(
        update={
            "stamp": stamp,
            "note": note,
            "replay_of": f"{original.config}-{original.stamp}",
            "git": _git(),
            "prompt_versions": dict(PROMPT_VERSION),
            "judge_prompt_versions": dict(JUDGE_PROMPT_VERSION),
            "started_at": started_at.isoformat(timespec="seconds"),
            "duration_s": round(time.perf_counter() - started, 1),
        }
    )
    return _save(info, [record for record, _ in pairs], events.records, results_dir, new_dir, out)


def load_events(path: Path) -> list[EventRecord]:
    """A trace's events, with their tags split off."""
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        data = json.loads(line)
        data.pop("ts", None)
        events.append(
            EventRecord(
                event=data.pop("event"),
                key=data.pop("eval_key", None),
                phase=data.pop("eval_phase", "setup"),
                fields=data,
            )
        )
    return events


def load_sessions(trace_dir: Path, info: RunInfo) -> list[SessionRecord]:
    """A trace's session records, in the order they ran."""
    order = {
        f"{client}--{script}": index
        for index, (client, script) in enumerate(
            (client, script) for client in info.clients for script in info.scripts
        )
    }
    records = [
        SessionRecord.model_validate_json(path.read_text(encoding="utf-8"))
        for path in (trace_dir / SESSIONS).glob("*.json")
    ]
    return sorted(records, key=lambda record: order.get(record.key, len(order)))


def _save(
    info: RunInfo,
    records: Sequence[SessionRecord],
    events: Sequence[EventRecord],
    results_dir: Path,
    trace_dir: Path,
    out: TextIO,
) -> Path:
    metrics = compute(records, events)
    summary = RunSummary(
        **info.model_dump(), metrics=metrics.model_dump(mode="json"), sessions=list(records)
    )
    sessions_dir = trace_dir / SESSIONS
    sessions_dir.mkdir(parents=True, exist_ok=True)
    for record in records:
        _write_json(sessions_dir / f"{record.key}.json", record.model_dump(mode="json"))
    _write_json(trace_dir / RUN_FILE, info.model_dump(mode="json"))
    path = results_dir / f"{info.config}-{info.stamp}.json"
    _write_json(path, summary.model_dump(mode="json", exclude=SUMMARY_EXCLUDE))
    print_metrics(metrics, out)
    say(out, f"\nSummary: {_shown(path)}\nTraces:  {_shown(trace_dir)}/")
    return path


def print_metrics(metrics: Metrics, out: TextIO) -> None:
    """The run's key numbers, for the console log."""
    gate, client, coach, perf = metrics.gate, metrics.client, metrics.coach, metrics.perf
    say(out, "\nMetrics")
    say(
        out,
        f"  gate: precision {_ratio(gate.unlocks)} · recall {_ratio(gate.recall)}"
        f" · false unlocks {gate.false_by_script or '-'} · extraction {_ratio(gate.extraction)}"
        f" (unjudged {gate.extraction_unjudged}) · gate failed {gate.gate_failed}"
        f" · turn errors {gate.turn_errors}",
    )
    for unlock in gate.false_unlocks:
        say(
            out,
            f"    false unlock: {unlock.key} t{unlock.n} {unlock.fact_id}"
            f" ({'pitch' if unlock.by_pitch else unlock.quote}) after «{unlock.student}»",
        )
    for miss in gate.misses:
        say(out, f"    missed: {miss.key} {miss.fact_id} (unlocked at {miss.unlocked_at})")
    for extraction in gate.extractions:
        say(
            out,
            f"    extraction: {extraction.key} t{extraction.n} unlocked {extraction.unlocked}"
            f" revealed {extraction.revealed}",
        )
    say(
        out,
        f"  client: breaks {len(client.breaks)} (judge {_ratio(client.judge_breaks)},"
        f" pattern {client.pattern_breaks}) · regenerated {client.regenerated}"
        f" · fallback {_ratio(client.fallback)} · language mismatches {client.language_mismatch}"
        f" (retried {client.language_retried}, fixed {client.language_fixed})",
    )
    claims = ", ".join(
        f"{script} {stats.unsupported}/{stats.judged}" for script, stats in coach.claims.items()
    )
    say(
        out,
        f"  coach: reports {coach.reports} · degraded {coach.degraded}"
        f" · valid first {_ratio(coach.schema_valid_first)} · backfilled {coach.backfilled}"
        f" · missed-critical recall {_ratio(coach.missed_critical)}"
        f" · unsuitable flagged {_ratio(coach.unsuitable_flagged)}"
        f" · strong praise valid {_ratio(coach.strong_praise_valid)}",
    )
    say(out, f"  coach claims unsupported: {claims}")
    say(
        out,
        f"  guards: dropped {coach.dropped_by_reason or '-'} · cleared {coach.cleared or '-'}"
        f" · mixed script {coach.mixed_script} · needs after pitch {coach.needs_after_pitch}",
    )
    say(
        out,
        f"  arabic: address {coach.arabic_address or '-'} · client {coach.arabic_agreement or '-'}"
        f" · unjudged {coach.arabic_unjudged}",
    )
    warm = " · ".join(
        f"{role} {lat.p50_ms}/{lat.p95_ms} ms (n={lat.calls})" for role, lat in perf.warm.items()
    )
    say(
        out,
        f"  latency warm p50/p95: {warm}"
        f" · coach all {perf.coach_all.p50_ms}/{perf.coach_all.p95_ms} ms",
    )
    say(
        out,
        f"  tokens per session: {perf.tokens_per_session} · judge {perf.judge_calls} calls,"
        f" {perf.judge_seconds} s, failed {perf.judge_failed}",
    )


def say(stream: TextIO, line: str) -> None:
    """Console output of a CLI, not logging."""
    stream.write(line + "\n")
    stream.flush()


def main(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
    llm: LLMClient | None = None,
    judge_llm: LLMClient | None = None,
    configs: EvalConfigs | None = None,
    results_dir: Path = RESULTS_DIR,
    out: TextIO = sys.stdout,
) -> int:
    """Parse the arguments, run, and return the exit code."""
    args = parse_args(argv)
    configs = configs or load_configs()
    if args.config is not None and args.config not in configs.configs:
        say(sys.stderr, f"No config {args.config!r}. Configs: {', '.join(configs.configs)}")
        return 2
    if settings is None:
        try:
            settings = Settings()
        except ValidationError as exc:
            names = ", ".join(sorted({str(error["loc"][0]) for error in exc.errors()}))
            say(
                sys.stderr, f"Settings are missing or invalid ({names}). Copy .env.example to .env."
            )
            return 2
    configure_logging(secrets=[settings.LLM_API_KEY.get_secret_value()])
    scripts = [name.strip() for name in args.scripts.split(",") if name.strip()]
    unknown = [name for name in scripts if name not in get_args(ScriptName)]
    if unknown:
        say(sys.stderr, f"Unknown scripts: {', '.join(unknown)}. Scripts: {', '.join(SCRIPTS)}")
        return 2
    clients = (
        None if args.clients == "all" else [c.strip() for c in args.clients.split(",") if c.strip()]
    )
    try:
        return asyncio.run(
            _main(args, configs, settings, llm, judge_llm, clients, scripts, results_dir, out)
        )
    except ContentValidationError as exc:
        for message in exc.messages:
            say(sys.stderr, message)
        return 1


async def _main(
    args: argparse.Namespace,
    configs: EvalConfigs,
    settings: Settings,
    llm: LLMClient | None,
    judge_llm: LLMClient | None,
    clients: list[str] | None,
    scripts: list[str],
    results_dir: Path,
    out: TextIO,
) -> int:
    name = (
        args.config
        or RunInfo.model_validate_json((args.replay / RUN_FILE).read_text(encoding="utf-8")).config
    )
    config = configs.configs[name]
    # Listing the models emits no event, so this client needs no trace.
    probe = llm or OpenAICompatClient(with_overrides(settings, config, results_dir / TRACES))
    missing = await _missing_models(
        probe, [config.gate, config.client, config.coach, configs.judge.model]
    )
    if missing:
        say(sys.stderr, f"The endpoint doesn't offer: {', '.join(missing)}")
        return 2
    if args.replay is not None:
        await replay(
            args.replay,
            configs,
            settings=settings,
            llm=llm,
            judge_llm=judge_llm,
            note=args.note,
            results_dir=results_dir,
            out=out,
        )
    else:
        await run(
            name,
            configs,
            settings=settings,
            llm=llm,
            judge_llm=judge_llm,
            clients=clients,
            scripts=[script for script in SCRIPTS if script in scripts],
            note=args.note,
            results_dir=results_dir,
            out=out,
        )
    return 0


def _clients(
    settings: Settings,
    judge: JudgeConfig,
    events: CapturedEvents,
    llm: LLMClient | None,
    judge_llm: LLMClient | None,
) -> tuple[LLMClient, LLMClient]:
    """The run's model clients, unless given (tests): both write to the run's events."""
    return (
        llm or OpenAICompatClient(settings, events=events),
        judge_llm or OpenAICompatClient(judge_settings(settings, judge), events=events),
    )


async def _missing_models(llm: LLMClient, models: Sequence[str]) -> list[str]:
    try:
        offered = set(await llm.list_models())
    except LLMError:
        return []  # the first real call reports the problem with its own error
    return [model for model in dict.fromkeys(models) if model not in offered]


def _stamp(results_dir: Path, config: str, when: datetime) -> str:
    stamp = when.strftime("%Y%m%d-%H%M")
    candidate, suffix = stamp, 2
    while (results_dir / f"{config}-{candidate}.json").exists():
        candidate, suffix = f"{stamp}-{suffix}", suffix + 1
    return candidate


def _settings_used(settings: Settings) -> dict[str, Any]:
    names = (
        "LLM_MAX_RETRIES",
        "LLM_MAX_CONCURRENCY",
        "LLM_DISABLE_THINKING",
        "LLM_TIMEOUT_GATE_S",
        "LLM_TIMEOUT_CLIENT_S",
        "LLM_TIMEOUT_COACH_S",
        "MAX_UNLOCKS_PER_TURN",
        "CLIENT_HISTORY_TURNS",
    )
    return {name: getattr(settings, name) for name in names}


def _git() -> dict[str, Any]:
    def git(*args: str) -> str:
        done = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
        )
        return done.stdout.strip()

    return {
        "commit": git("rev-parse", "--short", "HEAD"),
        "dirty": bool(git("status", "--porcelain", "--untracked-files=no")),
    }


def _note_error(record: SessionRecord, what: str, error: str | None) -> None:
    if error is not None:
        record.judge.errors.append(f"{what}: {error}")


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_events(path: Path, events: Sequence[EventRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for event in events:
            line = {
                "event": event.event,
                "eval_key": event.key,
                "eval_phase": event.phase,
                **event.fields,
            }
            fh.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")


def _ratio(ratio: Any) -> str:
    return f"{ratio.num}/{ratio.den}"


def _shown(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main())
