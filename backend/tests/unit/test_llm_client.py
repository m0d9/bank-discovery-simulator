import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2
import pytest

from app.llm.client import OpenAICompatClient
from app.llm.errors import (
    LLMError,
    ModelTimeout,
    ModelUnavailable,
    OutputTruncated,
    RateLimited,
)
from app.llm.roles import Role
from app.llm.types import ChatMessage
from app.telemetry.events import EventLogger
from tests.conftest import TEST_API_KEY, SettingsFactory
from tests.mock_endpoint import MockEndpoint, completion, error, models
from tests.unit.conftest import LLMFactory

MESSAGES = [
    ChatMessage(role="system", content="You are a bank client."),
    ChatMessage(role="user", content="Hello?"),
]
ReadEvents = Callable[[], list[dict[str, Any]]]


async def chat(llm: OpenAICompatClient, role: Role = Role.CLIENT, **kwargs: Any) -> Any:
    kwargs.setdefault("max_tokens", 250)
    kwargs.setdefault("temperature", 0.7)
    return await llm.chat(role, MESSAGES, **kwargs)


# --- success path -------------------------------------------------------------------------


async def test_chat_returns_text_tokens_latency_and_sends_the_request(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(completion("Good morning.", prompt_tokens=21, completion_tokens=4))

    result = await chat(make_llm(), prompt_version="abc12345")

    assert result.text == "Good morning."
    assert result.role is Role.CLIENT
    assert result.model == "test-model"
    assert (result.prompt_tokens, result.completion_tokens) == (21, 4)
    assert result.latency_ms >= 0
    assert result.attempts == 1
    assert result.json_mode == "none"
    assert result.cached is False
    body = endpoint.chat_bodies[0]
    assert body["model"] == "test-model"
    assert body["max_tokens"] == 250
    assert body["temperature"] == 0.7
    assert body["messages"] == [
        {"role": "system", "content": "You are a bank client."},
        {"role": "user", "content": "Hello?"},
    ]
    assert body["reasoning_effort"] == "none"
    assert "response_format" not in body


async def test_each_role_uses_its_own_model_and_timeout(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(completion(), completion(), completion())
    llm = make_llm(LLM_MODEL_GATE="small", LLM_MODEL_COACH="big")

    results = [await chat(llm, role) for role in (Role.GATE, Role.CLIENT, Role.COACH)]

    assert [r.model for r in results] == ["small", "test-model", "big"]
    assert [b["model"] for b in endpoint.chat_bodies] == ["small", "test-model", "big"]
    timeouts = [r.extensions["timeout"]["read"] for r in endpoint.chat_requests]
    assert timeouts == [30, 90, 240]


async def test_explicit_model_overrides_the_role_model(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(completion())
    result = await chat(make_llm(LLM_MODEL_CLIENT="client-model"), model="picked")
    assert result.model == "picked"
    assert endpoint.chat_bodies[0]["model"] == "picked"


async def test_think_blocks_are_stripped_and_reasoning_field_is_ignored(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(
        completion(
            "<think>The student wants rates.</think>\n\nWe pay 2% on savings.",
            reasoning="a separate chain of thought",
        )
    )
    result = await chat(make_llm())
    assert result.text == "We pay 2% on savings."


async def test_thinking_parameter_is_not_sent_when_the_setting_is_off(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(completion())
    await chat(make_llm(LLM_DISABLE_THINKING=False))
    assert "reasoning_effort" not in endpoint.chat_bodies[0]


# --- retries ------------------------------------------------------------------------------


async def test_500_then_success_takes_two_attempts(
    make_llm: LLMFactory, endpoint: MockEndpoint, sleeps: list[float]
) -> None:
    endpoint.queue(error(500, "boom"), completion("fine"))

    result = await chat(make_llm())

    assert result.text == "fine"
    assert result.attempts == 2
    assert sleeps == [0.5]


async def test_backoff_doubles_and_adds_jitter(
    settings_factory: SettingsFactory, endpoint: MockEndpoint, events_path: Path
) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    llm = OpenAICompatClient(
        settings_factory(),
        http_client=endpoint.http_client(),
        events=EventLogger(events_path),
        sleep=fake_sleep,
        jitter=lambda: 1.0,
    )
    endpoint.queue(error(503), error(502), completion())

    result = await chat(llm)

    assert result.attempts == 3
    assert sleeps == [0.75, 1.25]  # 0.5 s and 1 s, each plus the full 0.25 s of jitter


async def test_429_honours_retry_after(
    make_llm: LLMFactory, endpoint: MockEndpoint, sleeps: list[float]
) -> None:
    endpoint.queue(error(429, "slow down", headers={"Retry-After": "3"}), completion())

    result = await chat(make_llm())

    assert result.attempts == 2
    assert sleeps == [3.0]


async def test_retry_after_is_capped_at_five_seconds(
    make_llm: LLMFactory, endpoint: MockEndpoint, sleeps: list[float]
) -> None:
    endpoint.queue(error(429, headers={"Retry-After": "120"}), completion())
    await chat(make_llm())
    assert sleeps == [5.0]


async def test_429_until_retries_run_out_raises_rate_limited(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(error(429), error(429), error(429))
    with pytest.raises(RateLimited):
        await chat(make_llm())
    assert len(endpoint.chat_requests) == 3


async def test_timeouts_raise_model_timeout_when_retries_run_out(
    make_llm: LLMFactory, endpoint: MockEndpoint, sleeps: list[float]
) -> None:
    endpoint.queue(*(httpx2.ReadTimeout("timed out") for _ in range(3)))

    with pytest.raises(ModelTimeout):
        await chat(make_llm())

    assert len(endpoint.chat_requests) == 3
    assert sleeps == [0.5, 1.0]


async def test_max_retries_setting_is_respected(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(httpx2.ReadTimeout("timed out"))
    with pytest.raises(ModelTimeout):
        await chat(make_llm(LLM_MAX_RETRIES=0))
    assert len(endpoint.chat_requests) == 1


async def test_refused_connection_raises_model_unavailable(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(*(httpx2.ConnectError("Connection refused") for _ in range(3)))

    with pytest.raises(ModelUnavailable) as info:
        await chat(make_llm())

    assert info.value.reason == "unreachable"
    assert len(endpoint.chat_requests) == 3


async def test_unknown_model_404_raises_model_unavailable_without_retrying(
    make_llm: LLMFactory, endpoint: MockEndpoint, sleeps: list[float]
) -> None:
    endpoint.queue(error(404, 'model "nope" not found, try pulling it first'))

    with pytest.raises(ModelUnavailable) as info:
        await chat(make_llm())

    assert info.value.reason == "not_found"
    assert len(endpoint.chat_requests) == 1
    assert sleeps == []


async def test_rejected_key_raises_model_unavailable_without_retrying(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(error(401, "Invalid API Key"))
    with pytest.raises(ModelUnavailable) as info:
        await chat(make_llm())
    assert info.value.reason == "auth"
    assert len(endpoint.chat_requests) == 1


@pytest.mark.parametrize("status", [400, 413, 422])
async def test_other_4xx_raise_llm_error_without_retrying(
    make_llm: LLMFactory, endpoint: MockEndpoint, status: int
) -> None:
    endpoint.queue(error(status, "Please reduce the length of the messages"))
    with pytest.raises(LLMError) as info:
        await chat(make_llm())
    assert type(info.value) is LLMError
    assert info.value.code == "LLM_ERROR"
    assert len(endpoint.chat_requests) == 1


# --- thinking parameter fallback ----------------------------------------------------------


async def test_rejected_reasoning_effort_is_dropped_retried_and_remembered(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(
        error(400, "`reasoning_effort` is not supported with this model"),
        completion("first"),
        completion("second"),
        completion("other model"),
    )
    llm = make_llm(LLM_MODEL_COACH="other-model")

    first = await chat(llm)
    second = await chat(llm)
    other = await chat(llm, Role.COACH)

    assert (first.text, first.attempts) == ("first", 2)
    assert (second.text, second.attempts) == ("second", 1)
    assert other.text == "other model"
    bodies = endpoint.chat_bodies
    assert bodies[0]["reasoning_effort"] == "none"
    assert "reasoning_effort" not in bodies[1]  # the retry drops it
    assert "reasoning_effort" not in bodies[2]  # remembered for this (base_url, model)
    assert bodies[3]["reasoning_effort"] == "none"  # a different model still gets it


async def test_a_400_about_something_else_is_not_mistaken_for_the_thinking_parameter(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(error(400, "messages: too many tokens"))
    with pytest.raises(LLMError):
        await chat(make_llm())
    assert len(endpoint.chat_requests) == 1


# --- truncation ---------------------------------------------------------------------------


async def test_empty_reply_cut_off_by_max_tokens_raises_output_truncated(
    make_llm: LLMFactory, endpoint: MockEndpoint, read_events: ReadEvents
) -> None:
    endpoint.queue(completion("", finish_reason="length", completion_tokens=64))

    with pytest.raises(OutputTruncated):
        await chat(make_llm(), Role.COACH, max_tokens=64)

    assert read_events()[-1]["outcome"] == "truncated"


async def test_reply_that_was_all_reasoning_when_cut_off_is_truncated(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(completion("<think>still reasoning when the limit hit", finish_reason="length"))
    with pytest.raises(OutputTruncated):
        await chat(make_llm())


async def test_reply_with_text_cut_off_by_max_tokens_is_returned(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(completion("We offer three acc", finish_reason="length"))
    result = await chat(make_llm())
    assert result.text == "We offer three acc"


# --- concurrency ---------------------------------------------------------------------------


@pytest.mark.parametrize("limit", [1, 2])
async def test_semaphore_caps_requests_in_flight(
    make_llm: LLMFactory, endpoint: MockEndpoint, limit: int
) -> None:
    in_flight = 0
    peak = 0

    async def slow(request: httpx2.Request) -> httpx2.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return completion()

    endpoint.queue(*([slow] * 4))
    llm = make_llm(LLM_MAX_CONCURRENCY=limit)

    await asyncio.gather(*(chat(llm) for _ in range(4)))

    assert peak == limit


# --- list_models -------------------------------------------------------------------------


async def test_list_models_returns_ids_with_a_short_timeout(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.models_reply = models("qwen3.5:4b", "gpt-oss:20b")
    assert await make_llm().list_models() == ["qwen3.5:4b", "gpt-oss:20b"]
    assert endpoint.requests[-1].extensions["timeout"]["read"] == 3


@pytest.mark.parametrize(
    ("reply", "expected", "reason"),
    [
        (httpx2.ConnectError("Connection refused"), ModelUnavailable, "unreachable"),
        (error(401, "Invalid API Key"), ModelUnavailable, "auth"),
        (error(500, "boom"), ModelUnavailable, "server_error"),
        (httpx2.ReadTimeout("timed out"), ModelTimeout, None),
    ],
)
async def test_list_models_raises_typed_errors_without_retrying(
    make_llm: LLMFactory,
    endpoint: MockEndpoint,
    reply: Any,
    expected: type[LLMError],
    reason: str | None,
) -> None:
    endpoint.models_reply = reply
    with pytest.raises(expected) as info:
        await make_llm().list_models()
    if reason is not None:
        assert isinstance(info.value, ModelUnavailable)
        assert info.value.reason == reason
    assert len(endpoint.requests) == 1


async def test_list_models_does_not_wait_for_a_busy_semaphore(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    release = asyncio.Event()

    async def long_coach_call(request: httpx2.Request) -> httpx2.Response:
        await release.wait()
        return completion("feedback")

    endpoint.queue(long_coach_call)
    endpoint.models_reply = models("m")
    llm = make_llm(LLM_MAX_CONCURRENCY=1)

    coach = asyncio.create_task(chat(llm, Role.COACH))
    await asyncio.sleep(0.01)  # let the coach call take the only slot
    assert await asyncio.wait_for(llm.list_models(), timeout=1) == ["m"]
    release.set()
    assert (await coach).text == "feedback"


# --- telemetry ------------------------------------------------------------------------------


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


SECRET_QUESTION = "My account number is 12345678, can I get a loan?"
SECRET_REPLY = "Our premium savings rate is 4.2 percent"


async def test_llm_call_events_hold_measurements_but_never_message_text(
    make_llm: LLMFactory, endpoint: MockEndpoint, events_path: Path, read_events: ReadEvents
) -> None:
    endpoint.queue(
        completion(SECRET_REPLY, prompt_tokens=1000, completion_tokens=500),
        error(404, f"model not found while answering {SECRET_QUESTION}"),
    )
    llm = make_llm(LLM_PRICE_INPUT_PER_MTOK=0.5, LLM_PRICE_OUTPUT_PER_MTOK=2.0)
    messages = [ChatMessage(role="user", content=SECRET_QUESTION)]

    await llm.chat(Role.CLIENT, messages, max_tokens=50, temperature=0, prompt_version="v1")
    with pytest.raises(ModelUnavailable):
        await llm.chat(Role.GATE, messages, max_tokens=50, temperature=0)

    ok, failed = read_events()
    assert set(ok) == {
        "ts",
        "event",
        "role",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "latency_ms",
        "attempts",
        "outcome",
        "json_mode",
        "est_cost_usd",
        "prompt_version",
    }
    assert ok["event"] == "llm_call"
    assert (ok["role"], ok["model"], ok["outcome"], ok["json_mode"]) == (
        "client",
        "test-model",
        "ok",
        "none",
    )
    assert (ok["prompt_tokens"], ok["completion_tokens"], ok["attempts"]) == (1000, 500, 1)
    assert ok["est_cost_usd"] == pytest.approx((1000 * 0.5 + 500 * 2.0) / 1_000_000)
    assert ok["prompt_version"] == "v1"
    assert (failed["role"], failed["outcome"], failed["attempts"]) == (
        "gate",
        "MODEL_UNAVAILABLE",
        1,
    )
    raw = _read_text(events_path)
    for text in (SECRET_QUESTION, "12345678", SECRET_REPLY, TEST_API_KEY):
        assert text not in raw


async def test_cost_estimate_is_null_without_prices(
    make_llm: LLMFactory, endpoint: MockEndpoint, read_events: ReadEvents
) -> None:
    endpoint.queue(completion())
    await chat(make_llm())
    assert read_events()[0]["est_cost_usd"] is None


async def test_tokens_add_up_across_retried_requests(
    make_llm: LLMFactory, endpoint: MockEndpoint, read_events: ReadEvents
) -> None:
    endpoint.queue(
        error(400, "unsupported parameter: reasoning_effort"),
        completion(prompt_tokens=30, completion_tokens=3),
    )
    result = await chat(make_llm())
    assert (result.prompt_tokens, result.completion_tokens, result.attempts) == (30, 3, 2)
    assert read_events()[0]["attempts"] == 2
