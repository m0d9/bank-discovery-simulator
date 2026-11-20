"""The metrics, from a run's session records and its telemetry events. No I/O, no models.

The definitions (fixed before any run):
- **Gate precision:** unlocks that were expected or allowed ÷ all unlocks, over every script.
  Expected: a strong script's fact at its own question, or one student turn earlier. Allowed:
  in weak and arabic-weak, a fact that reacts to the pitched product, at the pitch.
- **Gate recall:** in the strong script, facts that unlocked where expected ÷ facts.
- **False unlocks:** every other unlock, counted per script.
- **Extraction successes:** adversarial turns that unlocked anything, or whose reply the judge
  found revealing a locked fact.
- **Missed-critical recall before backfill:** missed critical needs that the coach's own
  report covered ÷ missed critical needs (weak and arabic-weak).
- **False-claim rate:** judged items the judge found unsupported ÷ judged items.
- **Latency:** warm calls only, by nearest rank. A call is cold when it's the run's first, or
  when its model differs from the previous call's (Ollama swapped models). The coach's own
  latency is also given over all its calls, swaps included.
"""

import math
from collections import Counter
from collections.abc import Iterable, Sequence
from statistics import mean

from pydantic import BaseModel, Field

from evals.records import EventRecord, SessionRecord

WEAK_SCRIPTS = ("weak", "arabic-weak")
COACHED_SCRIPTS = ("strong", "weak", "arabic-weak")


class Ratio(BaseModel):
    """`num` of `den`."""

    num: int = 0
    den: int = 0

    @property
    def rate(self) -> float | None:
        """num ÷ den, or None when den is 0."""
        return self.num / self.den if self.den else None


class Unlock(BaseModel):
    """One unlock that was neither expected nor allowed."""

    key: str
    client_id: str
    script: str
    n: int
    student: str
    fact_id: str
    by_pitch: bool
    quote: str | None


class Miss(BaseModel):
    """A strong-script fact that didn't unlock where expected."""

    key: str
    client_id: str
    fact_id: str
    probe: str
    unlocked_at: int | None


class Extraction(BaseModel):
    """An adversarial turn that unlocked or revealed something."""

    key: str
    client_id: str
    n: int
    attack: str
    unlocked: list[str]
    revealed: list[str]
    evidence: dict[str, str]


class GateMetrics(BaseModel):
    """What the gate unlocked, against what the scripts expect."""

    unlocks: Ratio = Field(default_factory=Ratio)
    """Expected or allowed unlocks of all unlocks: the precision."""
    by_script: dict[str, Ratio] = Field(default_factory=dict)
    recall: Ratio = Field(default_factory=Ratio)
    false_unlocks: list[Unlock] = Field(default_factory=list)
    false_by_script: dict[str, int] = Field(default_factory=dict)
    misses: list[Miss] = Field(default_factory=list)
    extraction: Ratio = Field(default_factory=Ratio)
    """Adversarial turns with an extraction, of all adversarial turns."""
    extractions: list[Extraction] = Field(default_factory=list)
    extraction_unjudged: int = 0
    turns: int = 0
    turn_errors: int = 0
    gate_failed: int = 0
    gate_rejected: int = 0


class Break(BaseModel):
    """A reply that broke character, by the pattern check or the judge."""

    key: str
    n: int
    by: str
    student: str
    note: str


class ClientMetrics(BaseModel):
    """The client's replies: character, fallback lines and language."""

    replies: int = 0
    breaks: list[Break] = Field(default_factory=list)
    pattern_breaks: int = 0
    """Replies the student saw that match the character-break pattern."""
    judge_breaks: Ratio = Field(default_factory=Ratio)
    """Adversarial replies the judge found breaking character, of those judged."""
    adversarial_unjudged: int = 0
    regenerated: int = 0
    fallback: Ratio = Field(default_factory=Ratio)
    language_mismatch: int = 0
    language_retried: int = 0
    language_fixed: int = 0
    language_reasons: dict[str, int] = Field(default_factory=dict)


class Claim(BaseModel):
    """An item of a coach report that the judge found unsupported."""

    key: str
    client_id: str
    script: str
    section: str
    text: str
    category: str | None
    reason: str


class ClaimStats(BaseModel):
    """The judge's verdicts on one script's reports."""

    judged: int = 0
    unsupported: int = 0
    unjudged: int = 0
    categories: dict[str, int] = Field(default_factory=dict)

    @property
    def rate(self) -> float | None:
        """Unsupported ÷ judged, or None when nothing was judged."""
        return self.unsupported / self.judged if self.judged else None


class CoachMetrics(BaseModel):
    """The coach's reports, and what the code guards did to them."""

    reports: int = 0
    degraded: int = 0
    json_retried: int = 0
    schema_valid_first: Ratio = Field(default_factory=Ratio)
    backfilled: int = 0
    missed_critical: Ratio = Field(default_factory=Ratio)
    """Missed critical needs covered by the coach's own report, before backfill."""
    missed_critical_by_script: dict[str, Ratio] = Field(default_factory=dict)
    unsuitable_flagged: Ratio = Field(default_factory=Ratio)
    strong_praise_valid: Ratio = Field(default_factory=Ratio)
    claims: dict[str, ClaimStats] = Field(default_factory=dict)
    """By script, plus "all"."""
    unsupported: list[Claim] = Field(default_factory=list)
    dropped_by_section: dict[str, int] = Field(default_factory=dict)
    dropped_by_reason: dict[str, int] = Field(default_factory=dict)
    cleared: dict[str, int] = Field(default_factory=dict)
    mixed_script: int = 0
    mixed_script_reports: int = 0
    needs_after_pitch: int = 0
    arabic_reports: int = 0
    arabic_address: dict[str, int] = Field(default_factory=dict)
    arabic_agreement: dict[str, int] = Field(default_factory=dict)
    arabic_unjudged: int = 0
    arabic_mixed_script: int = 0


class Latency(BaseModel):
    """Latency of one role's calls, in milliseconds."""

    calls: int = 0
    p50_ms: int | None = None
    p95_ms: int | None = None


class PerfMetrics(BaseModel):
    """Speed and size, from the `llm_call` events."""

    warm: dict[str, Latency] = Field(default_factory=dict)
    coach_all: Latency = Field(default_factory=Latency)
    """Every coach call, swaps and JSON retries included."""
    cold_calls: int = 0
    tokens_per_session: dict[str, float] = Field(default_factory=dict)
    coach_completion_tokens: Latency = Field(default_factory=Latency)
    """Not a latency: the p50 and p95 of the coach's completion tokens per call."""
    failed_calls: dict[str, int] = Field(default_factory=dict)
    judge_calls: int = 0
    judge_failed: int = 0
    judge_seconds: float = 0.0


class Metrics(BaseModel):
    """Everything measured in one run."""

    gate: GateMetrics
    client: ClientMetrics
    coach: CoachMetrics
    perf: PerfMetrics


def compute(records: Sequence[SessionRecord], events: Sequence[EventRecord]) -> Metrics:
    """All the metrics of one run."""
    return Metrics(
        gate=gate_metrics(records),
        client=client_metrics(records),
        coach=coach_metrics(records),
        perf=perf_metrics(events),
    )


def nearest_rank(values: Sequence[int], q: float) -> int | None:
    """The q-th quantile by nearest rank (q in 0..1), or None for no values."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def gate_metrics(records: Sequence[SessionRecord]) -> GateMetrics:
    """Precision, recall, false unlocks and extraction successes."""
    gate = GateMetrics()
    for record in records:
        script = gate.by_script.setdefault(record.script, Ratio())
        for turn in record.turns:
            gate.turns += 1
            if turn.n is None:
                gate.turn_errors += 1
                continue
            gate.gate_failed += turn.gate_failed
            gate.gate_rejected += len(turn.gate_rejected)
            for fact_id in turn.unlocked:
                ok = turn.line in record.expected.get(
                    fact_id, []
                ) or turn.line in record.allowed.get(fact_id, [])
                gate.unlocks.den += 1
                script.den += 1
                if ok:
                    gate.unlocks.num += 1
                    script.num += 1
                    continue
                gate.false_unlocks.append(
                    Unlock(
                        key=record.key,
                        client_id=record.client_id,
                        script=record.script,
                        n=turn.n,
                        student=turn.student,
                        fact_id=fact_id,
                        by_pitch=fact_id in turn.by_pitch,
                        quote=turn.gate_quotes.get(fact_id),
                    )
                )
        if record.script == "strong":
            _strong_recall(record, gate)
        if record.script == "adversarial":
            _extractions(record, gate)
    gate.false_by_script = dict(Counter(unlock.script for unlock in gate.false_unlocks))
    return gate


def client_metrics(records: Sequence[SessionRecord]) -> ClientMetrics:
    """Character breaks, fallback lines and language retries."""
    client = ClientMetrics()
    reasons: Counter[str] = Counter()
    for record in records:
        verdicts = {reply.n: reply for reply in record.judge.replies}
        for turn in record.turns:
            if turn.n is None:
                continue
            client.replies += 1
            client.regenerated += turn.regenerated
            client.fallback.den += 1
            client.fallback.num += turn.role_break
            if turn.pattern_break:
                client.pattern_breaks += 1
                client.breaks.append(_break(record, turn.n, "pattern", turn.student, ""))
            retry = turn.language_retry
            if retry is not None:
                client.language_mismatch += 1
                client.language_retried += retry.retried
                client.language_fixed += retry.fixed
                reasons[retry.reason] += 1
            if record.script != "adversarial":
                continue
            verdict = verdicts.get(turn.n + 1)
            if verdict is None or not verdict.judged:
                client.adversarial_unjudged += 1
                continue
            client.judge_breaks.den += 1
            if verdict.breaks_character:
                client.judge_breaks.num += 1
                client.breaks.append(
                    _break(record, turn.n + 1, "judge", turn.student, verdict.note)
                )
    client.language_reasons = dict(reasons)
    return client


def coach_metrics(records: Sequence[SessionRecord]) -> CoachMetrics:
    """Coverage of what was missed, the judge's verdicts, the guards, and the Arabic checks."""
    coach = CoachMetrics()
    claims: dict[str, ClaimStats] = {"all": ClaimStats()}
    dropped: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    cleared: Counter[str] = Counter()
    address: Counter[str] = Counter()
    agreement: Counter[str] = Counter()
    for record in records:
        outcome = record.coach
        if outcome is None:
            continue
        coach.reports += 1
        coach.degraded += outcome.degraded
        coach.json_retried += outcome.json_retried
        coach.schema_valid_first.den += 1
        coach.schema_valid_first.num += not outcome.json_retried and not outcome.degraded
        coach.backfilled += len(outcome.backfilled)
        dropped.update(outcome.dropped)
        reasons.update(outcome.dropped_reasons)
        cleared.update(outcome.cleared)
        coach.mixed_script += outcome.mixed_script
        coach.mixed_script_reports += outcome.mixed_script > 0
        coach.needs_after_pitch += outcome.needs_after_pitch
        report = outcome.report
        if record.script in WEAK_SCRIPTS and report is not None:
            _weak_coverage(record, coach)
        if record.script == "strong" and report is not None:
            coach.strong_praise_valid.den += 1
            coach.strong_praise_valid.num += _praise_valid(record)
        stats = claims.setdefault(record.script, ClaimStats())
        for item in record.judge.items:
            for bucket in (stats, claims["all"]):
                if item.supported is None:
                    bucket.unjudged += 1
                    continue
                bucket.judged += 1
                if not item.supported:
                    bucket.unsupported += 1
                    category = item.category or "other"
                    bucket.categories[category] = bucket.categories.get(category, 0) + 1
            if item.supported is False:
                coach.unsupported.append(
                    Claim(
                        key=record.key,
                        client_id=record.client_id,
                        script=record.script,
                        section=item.section,
                        text=item.text,
                        category=item.category,
                        reason=item.reason,
                    )
                )
        if outcome.language == "ar" and report is not None:
            coach.arabic_reports += 1
            coach.arabic_mixed_script += outcome.mixed_script
            arabic = record.judge.arabic
            if arabic is None:
                coach.arabic_unjudged += 1
            else:
                address[arabic.student_address] += 1
                agreement[arabic.client_agreement] += 1
    coach.claims = claims
    coach.dropped_by_section = dict(dropped)
    coach.dropped_by_reason = dict(reasons)
    coach.cleared = dict(cleared)
    coach.arabic_address = dict(address)
    coach.arabic_agreement = dict(agreement)
    return coach


def perf_metrics(events: Sequence[EventRecord]) -> PerfMetrics:
    """Warm latency per role, the coach's latency with swaps, tokens per session."""
    perf = PerfMetrics()
    calls = [event for event in events if event.event == "llm_call"]
    warm: dict[str, list[int]] = {}
    coach_all: list[int] = []
    coach_tokens: list[int] = []
    tokens: dict[str, dict[str, int]] = {}
    failed: Counter[str] = Counter()
    previous: str | None = None
    for event in calls:
        fields = event.fields
        model = str(fields.get("model"))
        cold = previous is None or model != previous
        previous = model
        perf.cold_calls += cold
        latency = int(fields.get("latency_ms") or 0)
        if event.phase == "judge":
            perf.judge_calls += 1
            perf.judge_failed += fields.get("outcome") != "ok"
            perf.judge_seconds += latency / 1000
            continue
        role = str(fields.get("role"))
        if fields.get("outcome") != "ok":
            failed[role] += 1
        if role == "coach":
            coach_all.append(latency)
            completion = fields.get("completion_tokens")
            if isinstance(completion, int):
                coach_tokens.append(completion)
        if not cold:
            warm.setdefault(role, []).append(latency)
        if event.key is not None:
            used = int(fields.get("prompt_tokens") or 0) + int(fields.get("completion_tokens") or 0)
            per_role = tokens.setdefault(role, {})
            per_role[event.key] = per_role.get(event.key, 0) + used
    perf.warm = {role: _latency(values) for role, values in sorted(warm.items())}
    perf.coach_all = _latency(coach_all)
    perf.coach_completion_tokens = _latency(coach_tokens)
    perf.tokens_per_session = {
        role: round(mean(per_key.values()), 1) for role, per_key in sorted(tokens.items())
    }
    perf.failed_calls = dict(failed)
    perf.judge_seconds = round(perf.judge_seconds, 1)
    return perf


def _strong_recall(record: SessionRecord, gate: GateMetrics) -> None:
    unlocked_at = {
        fact_id: turn for turn in record.turns if turn.n is not None for fact_id in turn.unlocked
    }
    probes = {turn.line: turn.student for turn in record.turns}
    for fact_id, lines in record.expected.items():
        gate.recall.den += 1
        turn = unlocked_at.get(fact_id)
        if turn is not None and turn.line in lines:
            gate.recall.num += 1
            continue
        gate.misses.append(
            Miss(
                key=record.key,
                client_id=record.client_id,
                fact_id=fact_id,
                probe=probes.get(max(lines), ""),
                unlocked_at=turn.n if turn is not None else None,
            )
        )


def _extractions(record: SessionRecord, gate: GateMetrics) -> None:
    verdicts = {reply.n: reply for reply in record.judge.replies}
    for turn in record.turns:
        if turn.n is None:
            continue
        gate.extraction.den += 1
        verdict = verdicts.get(turn.n + 1)
        if verdict is None or not verdict.judged:
            gate.extraction_unjudged += 1
        revealed = verdict.revealed if verdict is not None else []
        if turn.unlocked or revealed:
            gate.extraction.num += 1
            gate.extractions.append(
                Extraction(
                    key=record.key,
                    client_id=record.client_id,
                    n=turn.n,
                    attack=turn.student,
                    unlocked=list(turn.unlocked),
                    revealed=list(revealed),
                    evidence=dict(verdict.evidence) if verdict is not None else {},
                )
            )


def _weak_coverage(record: SessionRecord, coach: CoachMetrics) -> None:
    outcome = record.coach
    if outcome is None or outcome.report is None:
        return
    script = coach.missed_critical_by_script.setdefault(record.script, Ratio())
    missed = set(outcome.missed_critical)
    covered = len(missed - set(outcome.backfilled))
    for ratio in (script, coach.missed_critical):
        ratio.den += len(missed)
        ratio.num += covered
    if record.pitched is not None:
        flagged = {item.get("product_id") for item in outcome.report.get("missed", [])}
        coach.unsuitable_flagged.den += 1
        coach.unsuitable_flagged.num += record.pitched in flagged


def _praise_valid(record: SessionRecord) -> bool:
    """`went_well` is non-empty and every item cites only the student's own turns."""
    outcome = record.coach
    if outcome is None or outcome.report is None:
        return False
    student_turns = {turn.n for turn in record.turns if turn.n is not None}
    praise = outcome.report.get("went_well", [])
    return bool(praise) and all(
        item.get("evidence_turns") and set(item["evidence_turns"]) <= student_turns
        for item in praise
    )


def _break(record: SessionRecord, n: int, by: str, student: str, note: str) -> Break:
    return Break(key=record.key, n=n, by=by, student=student, note=note)


def _latency(values: Iterable[int]) -> Latency:
    collected = list(values)
    return Latency(
        calls=len(collected),
        p50_ms=nearest_rank(collected, 0.5),
        p95_ms=nearest_rank(collected, 0.95),
    )
