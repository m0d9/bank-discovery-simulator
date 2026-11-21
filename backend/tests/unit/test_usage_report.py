"""scripts/usage_report.py: the faculty's usage report, from the telemetry events alone."""

import importlib.util
import io
import json
import shutil
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.content import load_registry
from app.llm import Role, llm_dep
from app.llm.fake import FakeLLM
from app.main import create_app
from tests.coaching_factory import coach_reply, missed_item
from tests.conftest import SettingsFactory
from tests.content_factory import ContentDir, client_data
from tests.interview_factory import gate_reply, real_quote
from tests.no_leak import find_text_leaks

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "usage_report.py"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "usage-events.jsonl"


def load_report() -> ModuleType:
    spec = importlib.util.spec_from_file_location("usage_report_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fixture_settings(settings_factory: SettingsFactory, content: ContentDir) -> Settings:
    """The fixture events, with the test content and a second client nobody interviewed."""
    content.write("clients/idle-client.yaml", client_data("idle-client"))
    settings = settings_factory(CONTENT_DIR=content.root)
    settings.DATA_DIR.mkdir(parents=True)
    shutil.copy(FIXTURE, settings.DATA_DIR / "events.jsonl")
    return settings


def run(settings: Settings, *argv: str) -> str:
    out = io.StringIO()
    assert load_report().main(list(argv), settings=settings, out=out) == 0
    return out.getvalue()


def write_events(settings: Settings, *events: dict[str, object]) -> None:
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(event) for event in events]
    (settings.DATA_DIR / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


SESSIONS = """\
| Stage | Sessions | Share of started | Median student turns |
| --- | ---: | ---: | ---: |
| Started | 4 | 100% | – |
| Interviewed | 3 | 75% | 2 |
| Reached wrap-up | 2 | 50% | 2.5 |
| Reached feedback | 2 | 50% | 2.5 |
"""

# Every fact in the content gets a row, found or not; ids no longer in the content still count.
DISCOVERY = """\
### Test Client (`test-client`)

2 interviews, 2 wrapped up.

| Hidden fact | Importance | Found in |
| --- | --- | ---: |
| `cash-gap` | critical | 2 of 2 (100%) |
| `expansion` | important | 0 of 2 (0%) |
| `renamed-fact` | no longer in the content | 1 of 2 (50%) |

### `retired-client` (no longer in the content)

1 interview, 0 wrapped up.

| Hidden fact | Importance | Found in |
| --- | --- | ---: |
| `old-fact` | – | 1 of 1 (100%) |

No interviews yet with `idle-client`.
"""

PER_TURN = (
    """\
| Gate model | Turns | Gate failures |
| --- | ---: | ---: |
| `model-a` | 4 | 0 (0.0%) |
| `model-b` | 2 | 1 (50.0%) |
""",
    """\
| Client model | Turns | Character breaks | Fallback line |
| --- | ---: | ---: | ---: |
| `model-a` | 6 | 2 (33.3%) | 1 (16.7%) |
""",
)

# Nearest rank: client p50 is the 4th of 8 calls, p95 the 8th. The smoke check's 5 s and 60 s
# calls and the judge's 30 s call would change these if they were counted.
LATENCY = """\
| Role | Model | Calls | p50 | p95 |
| --- | --- | ---: | ---: | ---: |
| gate | `model-a` | 4 | 0.8 s | 1.0 s |
| gate | `model-b` | 2 | 0.3 s | 0.5 s |
| client | `model-a` | 8 | 1.2 s | 1.6 s |
| coach | `model-a` | 2 | 9.0 s | 11.0 s |
"""

# Client: 12,800 input and 680 output tokens over 3 interviews.
TOKENS = """\
| Role | Model | Sessions | Input | Output | Total |
| --- | --- | ---: | ---: | ---: | ---: |
| gate | `model-a` | 2 | 2,150 | 100 | 2,250 |
| gate | `model-b` | 1 | 900 | 40 | 940 |
| client | `model-a` | 3 | 4,267 | 227 | 4,494 |
| coach | `model-a` | 2 | 4,100 | 950 | 5,050 |
"""

COST = (
    "$0.0415 in total, or $0.0138 per interview. 15 of 16 calls recorded a cost, with the"
    " prices configured when each one ran."
)


def test_the_report_counts_the_fixture(fixture_settings: Settings) -> None:
    text = run(fixture_settings)

    assert text.startswith("# Usage report\n\nFrom `")
    # The last event is at 01:30 on 2026-11-04 in +03:00: 22:30 UTC the day before.
    assert "events.jsonl`: 38 events from 2026-11-02 to 2026-11-03 (UTC).\n" in text
    assert SESSIONS in text
    assert DISCOVERY in text
    for table in PER_TURN:
        assert table in text
    assert LATENCY in text
    assert TOKENS in text
    assert COST in text
    # 3 smoke-check calls, the judge's, and one whose model name isn't a label.
    assert "are left out of latency, tokens and cost: 5 calls.\n" in text
    assert text.endswith("- 1 line of the events file couldn't be read.\n")


def test_message_text_in_the_events_never_reaches_the_report(fixture_settings: Settings) -> None:
    events = FIXTURE.read_text(encoding="utf-8")
    # The fixture holds every text field that LOG_TRANSCRIPTS=true adds, plus free text in a
    # model name and in a list of fact ids.
    for field in ("student_text", "client_text", "gate_note", "first_text", '"text"'):
        assert field in events
    # 6 turns × 3 texts, the first text, the dropped item, the model name and the fact id.
    assert events.count("TRANSCRIPT-") == 22

    assert "TRANSCRIPT" not in run(fixture_settings)


def test_out_writes_the_same_report_to_a_file(fixture_settings: Settings, tmp_path: Path) -> None:
    target = tmp_path / "reports" / "usage.md"

    said = run(fixture_settings, "--out", str(target))

    assert said == f"wrote {target}\n"
    assert target.read_text(encoding="utf-8") == run(fixture_settings)


def test_a_missing_events_file_is_an_error(
    settings_factory: SettingsFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    out = io.StringIO()

    code = load_report().main([], settings=settings_factory(), out=out)

    assert code == 1
    assert out.getvalue() == ""
    assert "No events yet:" in capsys.readouterr().err


def test_a_session_without_turns_has_nothing_to_measure(
    settings_factory: SettingsFactory, content: ContentDir
) -> None:
    settings = settings_factory(CONTENT_DIR=content.root)
    write_events(
        settings,
        {"ts": "2026-11-02T09:00:00+00:00", "event": "session_created", "session_id": "s-1"},
    )

    text = run(settings)

    assert "| Started | 1 | 100% | – |\n| Interviewed | 0 | 0% | – |\n" in text
    assert "No interviews yet.\n" in text
    assert "No student turns yet.\n" in text
    assert text.count("No model calls for interviews yet.\n") == 2
    # No prices: the report says which settings record a cost.
    assert "No estimate: no call recorded a cost" in text
    assert "`LLM_PRICE_INPUT_PER_MTOK` and `LLM_PRICE_OUTPUT_PER_MTOK`" in text


def test_a_report_reused_from_the_cache_is_not_a_coach_session(
    settings_factory: SettingsFactory, content: ContentDir
) -> None:
    # Two interviews with the same transcript: the second one's report comes from the cache.
    settings = settings_factory(CONTENT_DIR=content.root)
    events: list[dict[str, object]] = []
    for session_id, cached in (("s-1", False), ("s-2", True)):
        events.append(
            {
                "ts": "2026-11-02T09:00:00+00:00",
                "event": "turn",
                "session_id": session_id,
                "client_id": "test-client",
                "models": {"gate": "m", "client": "m"},
                "prompt_versions": {"gate": "g1", "client_system": "c1"},
            }
        )
        if not cached:
            events.append(
                {
                    "ts": "2026-11-02T09:01:00+00:00",
                    "event": "llm_call",
                    "role": "coach",
                    "model": "m",
                    "prompt_version": "k1",
                    "prompt_tokens": 4000,
                    "completion_tokens": 800,
                    "latency_ms": 9000,
                }
            )
        events.append(
            {
                "ts": "2026-11-02T09:02:00+00:00",
                "event": "feedback_generated",
                "session_id": session_id,
                "model": "m",
                "prompt_version": "k1",
                "cached": cached,
            }
        )
    write_events(settings, *events)

    assert "| coach | `m` | 1 | 4,000 | 800 | 4,800 |\n" in run(settings)


# Each text is distinctive, so finding it in the report means it leaked.
QUESTION = "PRIVATE-QUESTION how quickly do your customers pay you?"
FIRST_REPLY = "PRIVATE-FIRST-REPLY هذا رد باللغة العربية على سؤال مكتوب بالإنجليزية"
REPLY = "PRIVATE-REPLY some of them take three months."
GATE_NOTE = "PRIVATE-GATE-NOTE asks how they pay"
DROPPED = "PRIVATE-DROPPED praise that cites no student turn"


def test_transcripts_logged_by_a_whole_session_never_reach_the_report(
    settings_factory: SettingsFactory, fake_llm: FakeLLM, tmp_path: Path
) -> None:
    settings = settings_factory(FRONTEND_DIST=tmp_path / "missing", LOG_TRANSCRIPTS=True)
    app = create_app(settings)
    app.dependency_overrides[llm_dep] = lambda: fake_llm
    with TestClient(app) as api:
        created = api.post("/api/sessions", json={"client_id": "noura-al-kuwari", "language": "en"})
        url = f"/api/sessions/{created.json()['session_id']}"
        fake_llm.script(Role.GATE, gate_reply(real_quote("late-payments"), note=GATE_NOTE))
        # An Arabic reply to an English question is regenerated, and the first one is logged.
        fake_llm.script(Role.CLIENT, FIRST_REPLY, REPLY)
        assert api.post(f"{url}/messages", json={"text": QUESTION}).status_code == 200
        wrapup = {
            "needs_summary": "PRIVATE-SUMMARY she is paid late.",
            "recommendations": [
                {"product_id": "murabaha-working-capital", "reason": "PRIVATE-REASON cash gap."}
            ],
        }
        assert api.post(f"{url}/wrapup", json=wrapup).status_code == 200
        # Praise that cites no student turn is dropped, and its text logged.
        fake_llm.script(
            Role.COACH,
            coach_reply(
                went_well=[{"point": DROPPED, "evidence_turns": []}],
                missed=[missed_item("PRIVATE-MISSED you never asked about growth.")],
                summary="PRIVATE-SUMMARY-FEEDBACK your summary names the cash gap.",
            ),
        )
        assert api.post(f"{url}/feedback?lang=en").status_code == 200

    events = (settings.DATA_DIR / "events.jsonl").read_text(encoding="utf-8")
    for text in (QUESTION, FIRST_REPLY, REPLY, GATE_NOTE, DROPPED):
        assert text in events, text  # the premise: the events do hold the transcript
    target = tmp_path / "usage.md"
    printed = run(settings)
    run(settings, "--out", str(target))

    registry = load_registry(settings.CONTENT_DIR)
    for report in (printed, target.read_text(encoding="utf-8")):
        assert "| `late-payments` | critical | 1 of 1 (100%) |" in report
        assert "PRIVATE" not in report
        assert find_text_leaks(report, registry) == []
