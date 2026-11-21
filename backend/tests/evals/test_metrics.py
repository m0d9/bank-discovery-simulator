"""The metric definitions in evals/metrics.py, on hand-built records."""

from typing import Any

from evals.metrics import compute, gate_metrics, nearest_rank, perf_metrics
from evals.records import (
    ArabicJudgement,
    CoachRecord,
    EventRecord,
    ItemJudgement,
    JudgeRecord,
    ReplyJudgement,
    SessionRecord,
    TurnRecord,
)


def turn(line: int, *unlocked: str, by_pitch: tuple[str, ...] = (), **extra: Any) -> TurnRecord:
    return TurnRecord(
        line=line,
        kind="probe",
        student=f"line {line}",
        n=2 * line + 1,
        client="Fine.",
        unlocked=list(unlocked),
        by_pitch=list(by_pitch),
        gate_quotes={fact: f"asks about {fact}" for fact in unlocked if fact not in by_pitch},
        **extra,
    )


def strong(*turns: TurnRecord) -> SessionRecord:
    return SessionRecord(
        key="c--strong",
        client_id="c",
        script="strong",
        language="en",
        expected={"a": [0, 1], "b": [1, 2], "c": [2, 3]},
        turns=list(turns),
    )


def test_a_strong_fact_counts_at_its_question_or_one_turn_earlier_but_not_two() -> None:
    # `a` at its own question, `b` one turn early, `c` two turns early.
    record = strong(turn(0), turn(1, "a", "b"), turn(2), turn(3), turn(4))
    record.expected["c"] = [3, 4]
    record.turns[1] = turn(1, "a", "b", "c")

    gate = gate_metrics([record])

    assert (gate.recall.num, gate.recall.den) == (2, 3)
    assert (gate.unlocks.num, gate.unlocks.den) == (2, 3)
    assert [(u.fact_id, u.n) for u in gate.false_unlocks] == [("c", 3)]
    assert [(m.fact_id, m.unlocked_at) for m in gate.misses] == [("c", 3)]


def test_weak_allows_the_pitch_reaction_at_the_pitch_only() -> None:
    weak = SessionRecord(
        key="c--weak",
        client_id="c",
        script="weak",
        language="en",
        allowed={"sharia": [4]},
        turns=[turn(0), turn(1, "late"), turn(4, "sharia", by_pitch=("sharia",)), turn(5)],
    )
    late = weak.model_copy(update={"key": "d--weak", "client_id": "d"})
    late.turns = [turn(5, "sharia", by_pitch=("sharia",))]

    gate = gate_metrics([weak, late])

    assert (gate.unlocks.num, gate.unlocks.den) == (1, 3)
    assert gate.false_by_script == {"weak": 2}
    assert [(u.client_id, u.fact_id) for u in gate.false_unlocks] == [
        ("c", "late"),
        ("d", "sharia"),
    ]


def test_an_attack_extracts_by_unlocking_or_by_a_judged_reveal() -> None:
    attacks = SessionRecord(
        key="c--adversarial",
        client_id="c",
        script="adversarial",
        language="en",
        turns=[turn(0), turn(1, "secret"), turn(2), turn(3)],
        judge=JudgeRecord(
            replies=[
                ReplyJudgement(n=2, judged=True, breaks_character=False),
                ReplyJudgement(n=4, judged=True, breaks_character=False),
                ReplyJudgement(
                    n=6, judged=True, breaks_character=True, revealed=["other"], note="as an AI"
                ),
                ReplyJudgement(n=8, judged=False),
            ]
        ),
    )

    metrics = compute([attacks], [])

    gate, client = metrics.gate, metrics.client
    assert (gate.extraction.num, gate.extraction.den, gate.extraction_unjudged) == (2, 4, 1)
    assert [(e.n, e.unlocked, e.revealed) for e in gate.extractions] == [
        (3, ["secret"], []),
        (5, [], ["other"]),
    ]
    assert (client.judge_breaks.num, client.judge_breaks.den) == (1, 3)
    assert client.adversarial_unjudged == 1


def coached(script: str, *, backfilled: list[str], items: list[ItemJudgement]) -> SessionRecord:
    report = {
        "went_well": [{"point": "Asked about payments.", "evidence_turns": [1]}],
        "missed": [{"point": "The overdraft.", "need_id": None, "product_id": "od"}],
        "how_to_improve": [],
        "summary_feedback": "Fine.",
    }
    return SessionRecord(
        key=f"c--{script}",
        client_id="c",
        script=script,  # type: ignore[arg-type]
        language="en",
        pitched="od",
        turns=[turn(0)],
        coach=CoachRecord(
            language="ar" if script == "arabic-weak" else "en",
            model="m",
            prompt_version="v",
            degraded=False,
            json_retried=script == "weak",
            backfilled=backfilled,
            missed_critical=["gap", "growth"],
            mixed_script=1 if script == "arabic-weak" else 0,
            dropped_reasons={"no_student_turn": 1},
            report=report,
        ),
        judge=JudgeRecord(
            items=items,
            arabic=ArabicJudgement(student_address="masculine", client_agreement="matches")
            if script == "arabic-weak"
            else None,
        ),
    )


def item(supported: bool | None, category: str | None = None) -> ItemJudgement:
    return ItemJudgement(
        section="went_well", index=0, text="t", supported=supported, category=category
    )


def test_coach_metrics_count_before_backfill_and_judged_items_only() -> None:
    weak = coached(
        "weak", backfilled=["growth"], items=[item(True), item(False, "praise_not_shown")]
    )
    arabic = coached("arabic-weak", backfilled=[], items=[item(False, "invented"), item(None)])

    coach = compute([weak, arabic], []).coach

    assert (coach.missed_critical.num, coach.missed_critical.den) == (3, 4)
    assert (coach.unsuitable_flagged.num, coach.unsuitable_flagged.den) == (2, 2)
    assert (coach.schema_valid_first.num, coach.schema_valid_first.den) == (1, 2)
    all_claims = coach.claims["all"]
    assert (all_claims.judged, all_claims.unsupported, all_claims.unjudged) == (3, 2, 1)
    assert all_claims.categories == {"praise_not_shown": 1, "invented": 1}
    assert (coach.claims["weak"].unsupported, coach.claims["arabic-weak"].unsupported) == (1, 1)
    assert coach.dropped_by_reason == {"no_student_turn": 2}
    assert (coach.arabic_address, coach.arabic_agreement) == ({"masculine": 1}, {"matches": 1})
    assert (coach.mixed_script, coach.mixed_script_reports) == (1, 1)


def call(
    role: str, model: str, latency: int, *, phase: str = "interview", key: str = "k"
) -> EventRecord:
    fields = {
        "role": role,
        "model": model,
        "latency_ms": latency,
        "outcome": "ok",
        "prompt_tokens": 100,
        "completion_tokens": 10,
    }
    return EventRecord(event="llm_call", key=key, phase=phase, fields=fields)  # type: ignore[arg-type]


def test_a_call_after_a_model_swap_is_cold_and_the_coach_is_also_timed_with_its_swaps() -> None:
    events = [
        call("gate", "small", 9000),  # the run's first call: cold
        call("client", "small", 200),
        call("gate", "small", 100),
        call("coach", "big", 20000, phase="coach"),  # a swap: cold
        call("coach", "big", 5000, phase="coach"),
        call("gate", "small", 8000, key="k2"),  # swapping back: cold
        call("coach", "big", 30000, phase="judge"),  # the judge isn't a role here
    ]

    perf = perf_metrics(events)

    assert perf.cold_calls == 4
    assert {role: latency.calls for role, latency in perf.warm.items()} == {
        "client": 1,
        "coach": 1,
        "gate": 1,
    }
    assert (perf.coach_all.calls, perf.coach_all.p50_ms, perf.coach_all.p95_ms) == (2, 5000, 20000)
    assert perf.tokens_per_session == {"client": 110.0, "coach": 220.0, "gate": 165.0}
    assert (perf.judge_calls, perf.judge_seconds) == (1, 30.0)


def test_nearest_rank() -> None:
    assert nearest_rank([], 0.5) is None
    assert nearest_rank([5, 1, 3], 0.5) == 3
    assert nearest_rank(list(range(1, 21)), 0.95) == 19
    assert nearest_rank([7], 0.95) == 7
