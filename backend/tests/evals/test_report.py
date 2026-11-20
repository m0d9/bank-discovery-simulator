"""evals/report.py: which runs it shows, and what it writes between the markers."""

import io
from pathlib import Path
from typing import Any

import pytest
from evals.configs import EvalConfigs
from evals.metrics import compute
from evals.records import RunSummary, SessionRecord, TurnRecord
from evals.report import END, START, choose, main, render, write

from app.prompts import PROMPT_VERSION

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
                gate_quotes={
                    "needs-trucks": "follows up on his remark that the company has had to turn"
                    " down work"
                },
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
    notes = {"khalid-al-marri": {"needs-trucks": "By design (decided in M6)."}}

    text = render(CONFIGS, {"default": chosen}, notes)

    assert "| Gate precision" not in text  # labels are bold: "**Gate** precision"
    assert "| **Gate** precision (all scripts) | 0/1 (0%) |" in text
    assert (
        "`default` · weak: false unlock of `needs-trucks` at turn 3 («What brings you in"
        " today?»), quoting «follows up on his remark that the company has had to turn down"
        " work». *By design (decided in M6).*"
    ) in text
    assert "**Recommendation:** `default`: gate precision 0/1 (0%)" in text
    # Only a row whose coach is the judge is judged by its own model.
    assert "judged by its own model" not in text
    strong = choose([summary("strong-coach", "20261120-1930")], "strong-coach")
    assert strong is not None
    both = render(CONFIGS, {"default": chosen, "strong-coach": strong}, notes)
    assert "so that row's coach is judged by its own model" in both


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
