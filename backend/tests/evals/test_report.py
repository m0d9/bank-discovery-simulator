"""evals/report.py: which runs it shows, and what it writes between the markers."""

import io
from pathlib import Path
from typing import Any

import pytest
from evals.configs import EvalConfigs
from evals.metrics import compute
from evals.records import RunSummary, SessionRecord, TurnRecord
from evals.report import END, START, Note, choose, load_notes, main, render, write

from app.prompts import PROMPT_VERSION

FOLLOW_UP = "follows up on his remark that the company has had to turn down work"
CONFIGS = EvalConfigs.model_validate(
    {
        "recommended": "default",
        "judge": {"model": "big", "max_tokens": 4000, "max_retries": 4},
        "configs": {
            "default": {"gate": "small", "client": "small", "coach": "small"},
            "strong-coach": {"gate": "small", "client": "small", "coach": "big"},
        },
    }
)


def khalid_weak() -> SessionRecord:
    # His trucks unlock at a generic line, right after his hint.
    return SessionRecord(
        key="khalid-al-marri--weak",
        client_id="khalid-al-marri",
        script="weak",
        language="en",
        turns=[
            TurnRecord(line=0, kind="generic", student="Tell me about yourself.", n=1),
            TurnRecord(
                line=1,
                kind="generic",
                student="What brings you in today?",
                n=3,
                unlocked=["needs-trucks"],
                gate_quotes={"needs-trucks": FOLLOW_UP},
            ),
        ],
    )


def summary(config: str, stamp: str, **update: Any) -> RunSummary:
    records = [khalid_weak()]
    data: dict[str, Any] = {
        "config": config,
        "stamp": stamp,
        "models": {"gate": "small", "client": "small", "coach": "small"},
        "judge": {"model": "big"},
        "settings": {},
        "git": {"commit": "abc1234", "dirty": False},
        "prompt_versions": dict(PROMPT_VERSION),
        "judge_prompt_versions": {},
        "clients": ["khalid-al-marri"],
        "scripts": ["weak"],
        "complete": True,
        "started_at": f"2026-11-20T{stamp[-4:-2]}:{stamp[-2:]}:00+00:00",
        "duration_s": 600.0,
        "metrics": compute(records, []).model_dump(mode="json"),
        "sessions": records,
    }
    data.update(update)
    return RunSummary.model_validate(data)


def test_the_latest_complete_run_with_the_current_prompts_is_chosen() -> None:
    old_prompts = {**PROMPT_VERSION, "coach": "00000000"}
    runs = [
        summary("default", "20261120-1900"),
        summary("default", "20261120-2000", prompt_versions=old_prompts),
        summary("default", "20261120-2100", complete=False),
    ]

    chosen = choose(runs, "default")

    assert chosen is not None and (chosen.summary.stamp, chosen.current) == ("20261120-1900", True)
    stale = choose(runs[1:2], "default")
    assert stale is not None and stale.current is False
    assert choose(runs, "strong-coach") is None


def test_the_section_has_the_table_the_notes_and_the_recommendation() -> None:
    chosen = choose([summary("default", "20261120-1900")], "default")
    assert chosen is not None
    notes = {
        "khalid-al-marri": {
            "needs-trucks": Note(quote=FOLLOW_UP, note="By design (decided in PR #7).")
        }
    }

    text = render(CONFIGS, {"default": chosen}, notes)

    assert "| Gate precision" not in text  # labels are bold: "**Gate** precision"
    assert "| **Gate** precision (all scripts) | 0/1 (0%) |" in text
    assert (
        "`default` · weak: false unlock of `needs-trucks` at turn 3 («What brings you in"
        " today?»), quoting «follows up on his remark that the company has had to turn down"
        " work». *By design (decided in PR #7).*"
    ) in text
    assert "**Recommendation:** `default`: gate precision 0/1 (0%)" in text
    # Only a row whose coach is the judge is judged by its own model.
    assert "judged by its own model" not in text
    strong = choose([summary("strong-coach", "20261120-1930")], "strong-coach")
    assert strong is not None
    both = render(CONFIGS, {"default": chosen, "strong-coach": strong}, notes)
    assert "so that row's coach is judged by its own model" in both


def test_a_run_with_older_prompts_is_labelled_and_no_commit_is_shown() -> None:
    older_coach = {**PROMPT_VERSION, "coach": "00000000"}
    run = summary(
        "default",
        "20261120-1900",
        prompt_versions=older_coach,
        git={"commit": "abc1234", "dirty": True},
    )
    stale = choose([run], "default")
    assert stale is not None and stale.current is False

    text = render(CONFIGS, {"default": stale}, {})

    assert "| Setup | Run | Coach prompt | Notes |" in text
    assert (
        "| `default` | `default-20261120-1900` | `00000000`"
        " | **baseline run, older coach prompt** |"
    ) in text
    assert "|  | `default` (baseline run, older coach prompt) |" in text
    assert "abc1234" not in text and "uncommitted" not in text

    older_two = {**older_coach, "gate": "00000000"}
    both = choose([summary("default", "20261120-1900", prompt_versions=older_two)], "default")
    assert both is not None
    assert "baseline run, older gate and coach prompts" in render(CONFIGS, {"default": both}, {})


def test_write_replaces_only_the_section_between_the_markers(tmp_path: Path) -> None:
    doc = tmp_path / "evaluation.md"
    doc.write_text(f"# Evaluation\n\nKept.\n\n{START}\nold\n{END}\n\n## Prompt iterations\n")

    write("new", doc)

    assert doc.read_text() == (
        f"# Evaluation\n\nKept.\n\n{START}\nnew\n{END}\n\n## Prompt iterations\n"
    )


def test_write_creates_the_document_and_refuses_one_without_markers(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "evaluation.md"
    write("section", doc)
    assert f"{START}\nsection\n{END}" in doc.read_text()

    doc.write_text("no markers\n")
    with pytest.raises(ValueError, match="markers"):
        write("section", doc)


def test_main_reports_which_runs_it_used(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    (results / "default-20261120-1900.json").write_text(
        summary("default", "20261120-1900").model_dump_json()
    )
    out = io.StringIO()

    main(results_dir=results, doc=tmp_path / "evaluation.md", configs=CONFIGS, out=out)

    assert out.getvalue() == "default: default-20261120-1900\nNo complete run yet: strong-coach\n"


def test_an_explanation_never_goes_next_to_an_attacks_unlock() -> None:
    attack = khalid_weak().model_copy(update={"key": "khalid-al-marri--adversarial"})
    attack.script = "adversarial"
    run = summary("default", "20261120-1900", sessions=[attack])
    run.metrics = compute([attack], []).model_dump(mode="json")
    chosen = choose([run], "default")
    assert chosen is not None

    note = Note(quote=FOLLOW_UP, note="By design.")
    text = render(CONFIGS, {"default": chosen}, {"khalid-al-marri": {"needs-trucks": note}})

    assert "adversarial: false unlock of `needs-trucks` at turn 3" in text
    assert "By design." not in text


def test_an_explanation_goes_only_next_to_the_unlock_it_explains() -> None:
    other_quote = khalid_weak()
    other_quote.turns[1].gate_quotes["needs-trucks"] = "asks whether the company needs new vehicles"
    run = summary("default", "20261120-1900", sessions=[other_quote])
    run.metrics = compute([other_quote], []).model_dump(mode="json")
    chosen = choose([run], "default")
    assert chosen is not None

    note = Note(quote=FOLLOW_UP, note="By design.")
    text = render(CONFIGS, {"default": chosen}, {"khalid-al-marri": {"needs-trucks": note}})

    assert "quoting «asks whether the company needs new vehicles»." in text
    assert "By design." not in text


def test_the_real_notes_file_loads() -> None:
    notes = load_notes()
    assert notes["khalid-al-marri"]["needs-trucks"].quote == FOLLOW_UP
