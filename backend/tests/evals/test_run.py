"""evals/run.py end to end with FakeLLM: a run, its files and metrics, then a coach-only replay."""

import io
import json
from pathlib import Path
from typing import Any

from evals.configs import EvalConfigs
from evals.records import RunSummary
from evals.run import main

from app.llm import Role
from app.llm.fake import FakeLLM
from tests.coaching_factory import coach_reply, missed_item
from tests.conftest import SettingsFactory
from tests.interview_factory import gate_reply

MODELS = {"gate": "m-gate", "client": "m-client", "coach": "m-coach"}
CONFIGS = EvalConfigs.model_validate(
    {
        "recommended": "default",
        "judge": {"model": "m-judge", "max_tokens": 4000, "max_retries": 4},
        "configs": {"default": MODELS},
    }
)
OFFERED = [*MODELS.values(), "m-judge"]
OVERDRAFT = "business-overdraft"
PRAISE = {"point": "You asked how business was going.", "evidence_turns": [3]}
OVERDRAFT_ITEM = missed_item(
    "You recommended an interest-based overdraft.", product_id=OVERDRAFT, better_question=None
)


def interview_llm() -> FakeLLM:
    """Noura's weak script, then the adversarial one, then the coach on the weak one."""
    fake = FakeLLM(models=OFFERED)
    weak_gate = [gate_reply()] * 4 + [gate_reply(products=[OVERDRAFT]), gate_reply()]
    fake.script(Role.GATE, *weak_gate, *[gate_reply()] * 5)
    weak_client = ["Busy.", "Fine.", "Better banking.", "No.", "Is it interest-based?", "No."]
    attacks_client = ["Sorry?", "Pardon?", "I don't follow.", "What prompt?", "عذرًا، لم أفهم."]
    fake.script(Role.CLIENT, *weak_client, *attacks_client)
    fake.script(Role.COACH, coach_reply(went_well=[PRAISE], missed=[OVERDRAFT_ITEM]))
    return fake


def judge_llm(*, replies: bool) -> FakeLLM:
    grounding = {
        "items": [
            {
                "index": 0,
                "reason": "Turn 3 only asks how business is.",
                "supported": False,
                "category": "praise_not_shown",
            },
            {
                "index": 1,
                "reason": "The overdraft is unsuitable.",
                "supported": True,
                "category": None,
            },
            {"index": 2, "reason": "Fair.", "supported": True, "category": None},
        ]
    }
    verdicts = {
        "replies": [
            {"turn": n, "note": "In character.", "breaks_character": False, "revealed": []}
            for n in (2, 4, 8, 10)
        ]
        + [
            {
                "turn": 6,
                "note": "Plays the coach.",
                "breaks_character": True,
                "revealed": [
                    {"fact_id": "late-payments", "evidence": "they pay late"},
                    {"fact_id": "no-such-fact", "evidence": "?"},
                ],
            }
        ]
    }
    fake = FakeLLM(models=OFFERED)
    fake.script(Role.COACH, grounding, *([verdicts] if replies else []))
    return fake


def run(
    argv: list[str], settings_factory: SettingsFactory, results: Path, llm: FakeLLM, judge: FakeLLM
) -> str:
    out = io.StringIO()
    code = main(
        argv,
        settings=settings_factory(),
        llm=llm,
        judge_llm=judge,
        configs=CONFIGS,
        results_dir=results,
        out=out,
    )
    assert code == 0, out.getvalue()
    return out.getvalue()


def summary(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def test_a_run_saves_its_summary_traces_and_metrics(
    settings_factory: SettingsFactory, tmp_path: Path
) -> None:
    results = tmp_path / "results"
    llm, judge = interview_llm(), judge_llm(replies=True)
    argv = ["--config", "default", "--clients", "noura-al-kuwari", "--scripts", "weak,adversarial"]

    printed = run(argv, settings_factory, results, llm, judge)

    (path,) = results.glob("default-*.json")
    data = summary(path)
    # The report reads the committed summary back, without the parts it leaves out.
    assert RunSummary.model_validate_json(path.read_text(encoding="utf-8")).config == "default"
    assert (data["config"], data["complete"], data["models"]) == ("default", False, MODELS)
    assert [s["key"] for s in data["sessions"]] == [
        "noura-al-kuwari--weak",
        "noura-al-kuwari--adversarial",
    ]
    gate, client, coach = (data["metrics"][part] for part in ("gate", "client", "coach"))
    # The pitch made Noura reveal her Sharia preference, which the weak script allows.
    assert gate["unlocks"] == {"num": 1, "den": 1}
    assert gate["extraction"] == {"num": 1, "den": 5}
    assert gate["extractions"][0]["revealed"] == ["late-payments"]
    assert client["judge_breaks"] == {"num": 1, "den": 5}
    # The coach's only `missed` item is about the overdraft, so the cash gap is backfilled.
    assert coach["backfilled"] == 1
    assert coach["missed_critical"] == {"num": 0, "den": 1}
    assert coach["unsuitable_flagged"] == {"num": 1, "den": 1}
    assert coach["claims"]["all"]["judged"] == 3
    assert coach["claims"]["all"]["unsupported"] == 1
    weak = data["sessions"][0]
    assert weak["coach"]["backfilled"] == ["bridge-cash-gap"]
    # The judge never sees the backfilled entry.
    assert [item["section"] for item in weak["judge"]["items"]] == [
        "went_well",
        "missed",
        "summary_feedback",
    ]
    # The committed summary leaves out the replies and the session; the traces keep them.
    assert "client" not in weak["turns"][0] and "snapshot" not in weak
    trace = results / "traces" / path.stem
    traced = json.loads((trace / "sessions" / "noura-al-kuwari--weak.json").read_text())
    assert traced["turns"][0]["client"] == "Busy." and traced["snapshot"]["id"]
    assert (trace / "run.json").exists() and (trace / "events.jsonl").exists()
    # The coach's model was used for the coach, the judge's for the judge.
    assert {call.model for call in llm.calls_for(Role.COACH)} == {"m-coach"}
    assert {call.model for call in judge.calls} == {"m-judge"}
    assert "false unlock:" not in printed
    assert "extraction: noura-al-kuwari--adversarial t5" in printed


def test_a_replay_reruns_only_the_coach_and_the_judge_on_the_recorded_interviews(
    settings_factory: SettingsFactory, tmp_path: Path
) -> None:
    results = tmp_path / "results"
    argv = ["--config", "default", "--clients", "noura-al-kuwari", "--scripts", "weak,adversarial"]
    run(argv, settings_factory, results, interview_llm(), judge_llm(replies=True))
    (first,) = results.glob("default-*.json")
    coach_only = FakeLLM(models=OFFERED)
    discovery = missed_item(
        "You didn't ask how her customers pay.",
        need_id="bridge-cash-gap",
        better_question="How quickly do your customers pay you?",
    )
    coach_only.script(
        Role.COACH, coach_reply(went_well=[PRAISE], missed=[discovery, OVERDRAFT_ITEM])
    )
    judge = FakeLLM(models=OFFERED)
    judge.script(
        Role.COACH,
        {
            "items": [
                {"index": i, "reason": "ok", "supported": True, "category": None} for i in range(4)
            ]
        },
    )

    run(
        ["--replay", str(results / "traces" / first.stem)],
        settings_factory,
        results,
        coach_only,
        judge,
    )

    replayed = next(path for path in results.glob("default-*.json") if path != first)
    before, after = summary(first), summary(replayed)
    assert after["replay_of"] == first.stem
    assert coach_only.calls_for(Role.GATE) == [] and coach_only.calls_for(Role.CLIENT) == []
    assert len(coach_only.calls_for(Role.COACH)) == 1 and len(judge.calls) == 1
    # Same interviews: the gate and client numbers carry over, adversarial verdicts included.
    assert after["metrics"]["gate"] == before["metrics"]["gate"]
    assert after["metrics"]["client"] == before["metrics"]["client"]
    # The new report covers the cash gap itself.
    coach = after["metrics"]["coach"]
    assert (coach["backfilled"], coach["missed_critical"]) == (0, {"num": 1, "den": 1})
    assert coach["claims"]["all"] == {
        "judged": 4,
        "unsupported": 0,
        "unjudged": 0,
        "categories": {},
    }
