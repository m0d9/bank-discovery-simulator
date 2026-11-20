"""The feedback and export endpoints: the state machine, idempotency, degraded feedback, and the
export's headers and sections."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.llm import InvalidOutput, Role, llm_dep
from app.llm.fake import FakeLLM
from app.main import create_app
from tests.api.test_sessions_api import WRAPUP, assert_error, send, start
from tests.coaching_factory import coach_reply, missed_item
from tests.conftest import SettingsFactory

OVERDRAFT = "business-overdraft"
REPORT = coach_reply(
    went_well=[{"point": "You asked how her customers pay.", "evidence_turns": [1]}],
    missed=[
        missed_item(
            "You never asked about her banking preferences.",
            need_id="bridge-cash-gap",
            product_id=OVERDRAFT,
            evidence_turns=[],
            better_question="Is Islamic banking important to you?",
        )
    ],
    how_to_improve=[{"tip": "Ask about values before you pitch.", "example": None}],
)


@pytest.fixture
def api(
    settings_factory: SettingsFactory, fake_llm: FakeLLM, tmp_path: Path
) -> Iterator[TestClient]:
    app = create_app(settings_factory(FRONTEND_DIST=tmp_path / "missing"))
    app.dependency_overrides[llm_dep] = lambda: fake_llm
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def wrapped_up(api: TestClient, fake: FakeLLM, recommend: str = OVERDRAFT) -> str:
    """A session with Noura where the student found `late-payments`, then wrapped up."""
    session_id = start(api)
    assert send(api, fake, session_id, unlock=["late-payments"]).status_code == 200
    wrapup = {
        "needs_summary": WRAPUP["needs_summary"],
        "recommendations": [{"product_id": recommend, "reason": "Flexible cash when needed."}],
    }
    assert api.post(f"/api/sessions/{session_id}/wrapup", json=wrapup).status_code == 200
    return session_id


def test_feedback_comes_only_after_the_wrap_up(api: TestClient, fake_llm: FakeLLM) -> None:
    session_id = start(api)

    assert_error(api.post(f"/api/sessions/{session_id}/feedback?lang=en"), "INVALID_STATE")
    assert_error(api.post("/api/sessions/no-such-session/feedback?lang=en"), "SESSION_NOT_FOUND")
    assert_error(api.post(f"/api/sessions/{session_id}/feedback?lang=fr"), "INVALID_INPUT")
    assert_error(api.post(f"/api/sessions/{session_id}/feedback"), "INVALID_INPUT")
    assert fake_llm.calls_for(Role.COACH) == []


def test_feedback_has_the_analysis_the_report_and_the_revealed_profile(
    api: TestClient, fake_llm: FakeLLM
) -> None:
    session_id = wrapped_up(api, fake_llm)
    fake_llm.script(Role.COACH, REPORT)

    response = api.post(f"/api/sessions/{session_id}/feedback?lang=en")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "session_id",
        "language",
        "analysis",
        "report",
        "degraded",
        "models",
        "generated_at",
        "wrapup",
        "revealed",
    }
    assert (body["session_id"], body["language"], body["degraded"]) == (session_id, "en", False)
    analysis = body["analysis"]
    assert [(need["need_id"], need["status"]) for need in analysis["needs"]] == [
        ("bridge-cash-gap", "partial"),
        ("finance-contract-stock", "missed"),
    ]
    (verdict,) = analysis["products"]
    assert (verdict["product_id"], verdict["verdict"]) == (OVERDRAFT, "unsuitable")
    assert verdict["reasons"][0]["reason"] == {
        "en": "Interest-based; conflicts with her Sharia preference.",
        "ar": "قائم على الفائدة، ويتعارض مع تفضيلها للمنتجات المتوافقة مع الشريعة.",
    }
    assert analysis["missed_opportunities"] == [
        {"product_id": "murabaha-working-capital", "needs": ["bridge-cash-gap"]},
        {"product_id": "business-collect-account", "needs": ["bridge-cash-gap"]},
    ]
    assert analysis["stats"]["critical_found"] == 1
    report = body["report"]
    assert report["went_well"] == [
        {"point": "You asked how her customers pay.", "evidence_turns": [1]}
    ]
    # The model's item names the overdraft, so it doesn't cover the need: the backfill adds the
    # discovery entry first, with the locked critical fact's example question.
    backfill, model_item = report["missed"]
    assert (backfill["need_id"], backfill["product_id"]) == ("bridge-cash-gap", None)
    assert backfill["better_question"] == (
        "Do you have any preferences about the kind of banking products you use?"
    )
    assert model_item["better_question"] == "Is Islamic banking important to you?"
    revealed = body["revealed"]
    assert [fact["unlocked_at_turn"] for fact in revealed["hidden_facts"]] == [1, None, None]
    assert revealed["hidden_facts"][0]["content"]["en"].startswith("Two government-linked")
    assert revealed["needs"][0]["description"]["ar"].startswith("سدّ الفجوة")
    assert revealed["persona"]["occupation"] == {
        "en": "Owner and managing director of a catering company",
        "ar": None,
    }
    assert body["wrapup"]["recommendations"][0]["product_id"] == OVERDRAFT
    assert api.get(f"/api/sessions/{session_id}").json()["status"] == "feedback_ready"


def test_asking_again_returns_the_same_feedback_without_another_coach_call(
    api: TestClient, fake_llm: FakeLLM
) -> None:
    session_id = wrapped_up(api, fake_llm)
    fake_llm.script(Role.COACH, REPORT)

    first = api.post(f"/api/sessions/{session_id}/feedback?lang=en")
    second = api.post(f"/api/sessions/{session_id}/feedback?lang=en")

    assert second.status_code == 200
    assert second.json() == first.json()
    assert len(fake_llm.calls_for(Role.COACH)) == 1


def test_degraded_feedback_keeps_the_analysis_and_asking_again_retries(
    api: TestClient, fake_llm: FakeLLM
) -> None:
    session_id = wrapped_up(api, fake_llm)
    fake_llm.script(Role.COACH, InvalidOutput("unusable JSON after one retry"), REPORT)

    degraded = api.post(f"/api/sessions/{session_id}/feedback?lang=en").json()
    retried = api.post(f"/api/sessions/{session_id}/feedback?lang=en").json()

    assert (degraded["degraded"], degraded["report"]) == (True, None)
    assert degraded["analysis"] == retried["analysis"]
    assert degraded["revealed"] == retried["revealed"]
    assert retried["degraded"] is False and retried["report"]["went_well"]


def test_the_export_is_a_markdown_attachment(api: TestClient, fake_llm: FakeLLM) -> None:
    session_id = wrapped_up(api, fake_llm)
    today = datetime.now(UTC).strftime("%Y%m%d")

    before = api.get(f"/api/sessions/{session_id}/export?format=md")
    fake_llm.script(Role.COACH, REPORT)
    api.post(f"/api/sessions/{session_id}/feedback?lang=ar")
    after = api.get(f"/api/sessions/{session_id}/export")

    assert before.status_code == 200
    assert before.headers["content-type"] == "text/markdown; charset=utf-8"
    assert before.headers["content-disposition"] == (
        f"attachment; filename=interview-noura-al-kuwari-{today}.md"
    )
    assert before.text.startswith("# Interview with Noura Al-Kuwari")
    assert "Two government-linked" not in before.text
    # The latest feedback was in Arabic, so the export is too.
    assert after.text.startswith('<div dir="rtl">\n\n# \u2068مقابلة مع نورة الكواري\u2069')
    assert "## خلف الكواليس: الملف الكامل للعميل" in after.text
    assert "Two government-linked" in after.text


def test_the_export_is_markdown_only(api: TestClient) -> None:
    session_id = start(api)

    assert_error(api.get(f"/api/sessions/{session_id}/export?format=pdf"), "INVALID_INPUT")
    assert_error(api.get("/api/sessions/no-such-session/export"), "SESSION_NOT_FOUND")
