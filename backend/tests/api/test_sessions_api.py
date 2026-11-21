import asyncio
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api.errors import ERROR_CODES, STATUS_BY_CODE
from app.llm import (
    ChatMessage,
    InvalidOutput,
    LLMError,
    LLMResult,
    ModelTimeout,
    ModelUnavailable,
    OutputTruncated,
    RateLimited,
    Role,
    llm_dep,
)
from app.llm.fake import FakeLLM
from app.main import create_app
from app.simulation import InterviewService
from tests.conftest import SettingsFactory
from tests.interview_factory import gate_reply, real_quote

NOURA = "noura-al-kuwari"
NOURA_OPENING = (
    "Hello. I don't have long, but a friend said I should talk to you about better "
    "banking for my business."
)
WRAPUP = {
    "needs_summary": "She is paid late by government clients and needs Islamic finance.",
    "recommendations": [
        {"product_id": "murabaha-working-capital", "reason": "Sharia-compliant stock finance."}
    ],
}
ApiFactory = Callable[..., TestClient]


@pytest.fixture
def api_factory(
    settings_factory: SettingsFactory, fake_llm: FakeLLM, tmp_path: Path
) -> Iterator[ApiFactory]:
    """Build a TestClient on the real content, with settings overrides and the shared FakeLLM."""
    clients: list[TestClient] = []

    def make(**overrides: Any) -> TestClient:
        settings = settings_factory(FRONTEND_DIST=tmp_path / "missing", **overrides)
        app = create_app(settings)
        app.dependency_overrides[llm_dep] = lambda: fake_llm
        test_client = TestClient(app, raise_server_exceptions=False)
        clients.append(test_client.__enter__())
        return test_client

    yield make
    for test_client in clients:
        test_client.__exit__(None, None, None)


@pytest.fixture
def api(api_factory: ApiFactory) -> TestClient:
    return api_factory()


def start(api: TestClient, language: str = "en") -> str:
    response = api.post("/api/sessions", json={"client_id": NOURA, "language": language})
    assert response.status_code == 201, response.text
    session_id: str = response.json()["session_id"]
    return session_id


def send(
    api: TestClient,
    fake: FakeLLM,
    session_id: str,
    text: str = "How quickly do your customers pay you?",
    *,
    unlock: Sequence[str] = (),
    reply: str = "Some of them take months, honestly.",
) -> httpx.Response:
    fake.script(Role.GATE, gate_reply(*(real_quote(fact_id) for fact_id in unlock)))
    fake.script(Role.CLIENT, reply)
    return api.post(f"/api/sessions/{session_id}/messages", json={"text": text})


def assert_error(response: httpx.Response, code: str) -> dict[str, Any]:
    assert response.status_code == STATUS_BY_CODE[code], response.text
    body: dict[str, Any] = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message_key", "detail"}
    assert body["error"]["code"] == code
    assert body["error"]["message_key"] == f"errors.{code}"
    return body["error"]


def test_the_full_interview_flow(api: TestClient, fake_llm: FakeLLM) -> None:
    created = api.post("/api/sessions", json={"client_id": NOURA, "language": "en"})
    assert created.status_code == 201
    body = created.json()
    session_id = body["session_id"]
    assert body["client"]["id"] == NOURA and set(body["client"]) == {
        "id",
        "segment",
        "difficulty",
        "name",
        "headline",
    }
    assert body["opening_line"]["en"] == NOURA_OPENING
    assert body["opening_line"]["ar"].startswith("السلام عليكم")
    assert (body["max_student_turns"], body["max_message_chars"]) == (30, 1000)
    assert body["models"] == {"gate": "test-model", "client": "test-model", "coach": "test-model"}

    first = send(api, fake_llm, session_id, unlock=["late-payments"])
    assert first.status_code == 200
    assert first.json() == {
        "student_turn": {
            "n": 1,
            "role": "student",
            "text": "How quickly do your customers pay you?",
        },
        "client_turn": {"n": 2, "role": "client", "text": "Some of them take months, honestly."},
        "student_turns_used": 1,
        "max_student_turns": 30,
    }
    assert send(api, fake_llm, session_id, "Anything else?").status_code == 200

    session = api.get(f"/api/sessions/{session_id}").json()
    assert session["status"] == "interviewing" and session["language"] == "en"
    assert [(t["n"], t["role"]) for t in session["turns"]] == [
        (0, "client"),
        (1, "student"),
        (2, "client"),
        (3, "student"),
        (4, "client"),
    ]
    assert session["turns"][0]["text"] == NOURA_OPENING
    assert all(set(turn) == {"n", "role", "text"} for turn in session["turns"])  # no unlocks
    assert session["student_turns_used"] == 2

    wrapped = api.post(f"/api/sessions/{session_id}/wrapup", json=WRAPUP)
    assert wrapped.status_code == 200 and wrapped.json()["status"] == "wrapped_up"
    assert api.get(f"/api/sessions/{session_id}").json()["status"] == "wrapped_up"

    deleted = api.delete(f"/api/sessions/{session_id}")
    assert deleted.status_code == 204 and deleted.content == b""
    assert_error(api.get(f"/api/sessions/{session_id}"), "SESSION_NOT_FOUND")


def test_an_arabic_session_opens_in_arabic(api: TestClient) -> None:
    session_id = start(api, "ar")
    turns = api.get(f"/api/sessions/{session_id}").json()["turns"]
    assert turns[0]["text"].startswith("السلام عليكم")


def test_the_limits_in_both_session_dtos_follow_the_settings(api_factory: ApiFactory) -> None:
    api = api_factory(MAX_STUDENT_TURNS=12, MAX_MESSAGE_CHARS=400)
    created = api.post("/api/sessions", json={"client_id": NOURA, "language": "en"}).json()
    session = api.get(f"/api/sessions/{created['session_id']}").json()

    for body in (created, session):
        assert (body["max_student_turns"], body["max_message_chars"]) == (12, 400)


@pytest.mark.parametrize(
    ("body", "problem"),
    [
        ({"client_id": "nobody", "language": "en"}, "UNKNOWN_CLIENT"),
        ({"client_id": NOURA, "language": "fr"}, "INVALID_INPUT"),
        ({"client_id": NOURA}, "INVALID_INPUT"),
    ],
)
def test_creating_a_session_validates_the_request(
    api: TestClient, body: dict[str, Any], problem: str
) -> None:
    error = assert_error(api.post("/api/sessions", json=body), problem)
    assert error["detail"]


def test_invalid_input_names_the_field_and_never_repeats_the_input(api: TestClient) -> None:
    error = assert_error(
        api.post("/api/sessions", json={"client_id": NOURA, "language": "SECRET-INPUT"}),
        "INVALID_INPUT",
    )
    assert error["detail"].startswith("language:")
    assert "SECRET-INPUT" not in error["detail"]


def test_a_body_that_is_not_json_is_invalid_input(api: TestClient) -> None:
    response = api.post(
        "/api/sessions", content=b"{not json", headers={"content-type": "application/json"}
    )
    assert_error(response, "INVALID_INPUT")


@pytest.mark.parametrize(("method", "suffix"), [("GET", ""), ("DELETE", "")])
def test_an_unknown_session_is_not_found(api: TestClient, method: str, suffix: str) -> None:
    assert_error(api.request(method, f"/api/sessions/nope{suffix}"), "SESSION_NOT_FOUND")


def test_messages_and_wrapups_for_an_unknown_session_are_not_found(api: TestClient) -> None:
    assert_error(api.post("/api/sessions/nope/messages", json={"text": "Hi"}), "SESSION_NOT_FOUND")
    assert_error(api.post("/api/sessions/nope/wrapup", json=WRAPUP), "SESSION_NOT_FOUND")


@pytest.mark.parametrize("text", ["", "   \n", "\x00\x07"])
def test_an_empty_message_is_invalid_input(api: TestClient, text: str) -> None:
    session_id = start(api)
    response = api.post(f"/api/sessions/{session_id}/messages", json={"text": text})
    assert assert_error(response, "INVALID_INPUT")["detail"] == "the message is empty"


def test_a_message_over_the_limit_is_invalid_input(
    api_factory: ApiFactory, fake_llm: FakeLLM
) -> None:
    api = api_factory(MAX_MESSAGE_CHARS=20)
    session_id = start(api)
    assert send(api, fake_llm, session_id, "x" * 20).status_code == 200
    response = api.post(f"/api/sessions/{session_id}/messages", json={"text": "x" * 21})
    assert "longer than 20 characters" in assert_error(response, "INVALID_INPUT")["detail"]


def test_the_turn_limit_returns_turn_limit(api_factory: ApiFactory, fake_llm: FakeLLM) -> None:
    api = api_factory(MAX_STUDENT_TURNS=1)
    session_id = start(api)
    assert send(api, fake_llm, session_id).status_code == 200

    response = api.post(f"/api/sessions/{session_id}/messages", json={"text": "One more?"})
    assert_error(response, "TURN_LIMIT")
    # Wrapping up is still allowed at the limit.
    assert api.post(f"/api/sessions/{session_id}/wrapup", json=WRAPUP).status_code == 200


def test_after_wrap_up_messages_and_a_second_wrap_up_are_invalid_state(
    api: TestClient, fake_llm: FakeLLM
) -> None:
    session_id = start(api)
    send(api, fake_llm, session_id)
    assert api.post(f"/api/sessions/{session_id}/wrapup", json=WRAPUP).status_code == 200

    message = api.post(f"/api/sessions/{session_id}/messages", json={"text": "One more?"})
    assert_error(message, "INVALID_STATE")
    assert_error(api.post(f"/api/sessions/{session_id}/wrapup", json=WRAPUP), "INVALID_STATE")


def test_wrap_up_needs_at_least_one_student_turn(api: TestClient) -> None:
    session_id = start(api)
    assert_error(api.post(f"/api/sessions/{session_id}/wrapup", json=WRAPUP), "INVALID_STATE")


@pytest.mark.parametrize(
    ("change", "detail"),
    [
        ({"needs_summary": "Too short."}, "needs_summary"),
        ({"recommendations": []}, "recommendations"),
        (
            {"recommendations": [{"product_id": f"p{i}", "reason": "Because."} for i in range(4)]},
            "recommendations",
        ),
        (
            {"recommendations": [WRAPUP["recommendations"][0]] * 2},
            "each product can be recommended only once",
        ),
        (
            {"recommendations": [{"product_id": "murabaha-working-capital", "reason": "ok"}]},
            "recommendations[0].reason",
        ),
        (
            {"recommendations": [{"product_id": "made-up", "reason": "Sounds good."}]},
            "unknown product 'made-up'",
        ),
    ],
)
def test_wrap_up_validation(
    api: TestClient, fake_llm: FakeLLM, change: dict[str, Any], detail: str
) -> None:
    session_id = start(api)
    send(api, fake_llm, session_id)

    response = api.post(f"/api/sessions/{session_id}/wrapup", json={**WRAPUP, **change})

    assert detail in assert_error(response, "INVALID_INPUT")["detail"]
    assert api.get(f"/api/sessions/{session_id}").json()["status"] == "interviewing"


@pytest.mark.parametrize(
    ("errors", "code"),
    [
        ([ModelUnavailable("cannot reach the model endpoint")], "MODEL_UNAVAILABLE"),
        ([ModelTimeout("the model did not answer in time")], "MODEL_TIMEOUT"),
        ([RateLimited("the endpoint is rate limiting (HTTP 429)")], "RATE_LIMITED"),
        ([OutputTruncated("x"), OutputTruncated("x")], "INVALID_OUTPUT"),
        (["", ""], "INVALID_OUTPUT"),
        ([LLMError("the endpoint rejected the request (HTTP 400)")], "LLM_ERROR"),
    ],
    ids=["unavailable", "timeout", "rate-limited", "truncated", "empty", "llm-error"],
)
def test_a_failed_client_reply_maps_to_its_code_and_saves_nothing(
    api: TestClient, fake_llm: FakeLLM, errors: list[Any], code: str
) -> None:
    session_id = start(api)
    fake_llm.script(Role.GATE, gate_reply(real_quote("late-payments")))
    fake_llm.script(Role.CLIENT, *errors)

    response = api.post(f"/api/sessions/{session_id}/messages", json={"text": "How do they pay?"})

    assert_error(response, code)
    session = api.get(f"/api/sessions/{session_id}").json()
    assert len(session["turns"]) == 1 and session["student_turns_used"] == 0


def test_a_failed_gate_still_gets_a_reply(api: TestClient, fake_llm: FakeLLM) -> None:
    session_id = start(api)
    fake_llm.script(Role.GATE, InvalidOutput("unusable JSON after one retry"))
    fake_llm.script(Role.CLIENT, "Sorry, I'm between events. What did you ask?")

    response = api.post(f"/api/sessions/{session_id}/messages", json={"text": "How do they pay?"})

    assert response.status_code == 200
    assert response.json()["client_turn"]["text"].startswith("Sorry, I'm between events")


class _SlowGate(FakeLLM):
    """A FakeLLM whose gate waits until released, so one turn stays in progress."""

    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def chat_json[T: BaseModel](
        self,
        role: Role,
        messages: Sequence[ChatMessage],
        schema: type[T],
        *,
        model: str | None = None,
        max_tokens: int,
        temperature: float = 0,
        prompt_version: str | None = None,
    ) -> tuple[T, LLMResult]:
        self.started.set()
        await self.release.wait()
        return await super().chat_json(
            role,
            messages,
            schema,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            prompt_version=prompt_version,
        )


async def test_a_session_mid_turn_is_busy(
    settings_factory: SettingsFactory, tmp_path: Path
) -> None:
    slow = _SlowGate()
    app = create_app(settings_factory(FRONTEND_DIST=tmp_path / "missing"))
    app.dependency_overrides[llm_dep] = lambda: slow
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
        created = await api.post("/api/sessions", json={"client_id": NOURA, "language": "en"})
        url = f"/api/sessions/{created.json()['session_id']}"
        slow.script(Role.GATE, gate_reply())
        slow.script(Role.CLIENT, "Some take months.")

        first = asyncio.create_task(api.post(f"{url}/messages", json={"text": "How do they pay?"}))
        await slow.started.wait()
        busy = [
            await api.post(f"{url}/messages", json={"text": "Hello?"}),
            await api.post(f"{url}/wrapup", json=WRAPUP),
            await api.delete(url),
        ]
        slow.release.set()
        done = await first

    for response in busy:
        assert_error(response, "SESSION_BUSY")
    assert done.status_code == 200


def test_an_unexpected_error_is_an_internal_error_without_details(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(self: InterviewService, session_id: str) -> None:
        raise RuntimeError("SECRET-DETAIL from deep inside")

    monkeypatch.setattr(InterviewService, "get_session", broken)

    response = api.get("/api/sessions/any")

    assert assert_error(response, "INTERNAL_ERROR")["detail"] is None
    assert "SECRET-DETAIL" not in response.text


def test_the_error_code_table() -> None:
    assert set(ERROR_CODES) == {
        "NOT_FOUND",
        "SESSION_NOT_FOUND",
        "UNKNOWN_CLIENT",
        "SESSION_BUSY",
        "TURN_LIMIT",
        "INVALID_STATE",
        "INVALID_INPUT",
        "REQUEST_TOO_LARGE",
        "MODEL_UNAVAILABLE",
        "MODEL_TIMEOUT",
        "RATE_LIMITED",
        "INVALID_OUTPUT",
        "LLM_ERROR",
        "INTERNAL_ERROR",
    }
    assert STATUS_BY_CODE["SESSION_BUSY"] == 409 and STATUS_BY_CODE["MODEL_TIMEOUT"] == 504


def test_the_openapi_schema_documents_the_error_envelope(api: TestClient) -> None:
    schema = api.get("/api/openapi.json").json()
    messages = schema["paths"]["/api/sessions/{session_id}/messages"]["post"]["responses"]

    assert set(messages) == {"200", "404", "409", "422", "429", "500", "502", "503", "504"}
    for status, response in messages.items():
        if status != "200":
            ref = response["content"]["application/json"]["schema"]["$ref"]
            assert ref.endswith("/ErrorEnvelopeDTO"), status
    assert "HTTPValidationError" not in schema["components"]["schemas"]
