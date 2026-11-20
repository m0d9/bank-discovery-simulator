from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel

from app.llm.errors import InvalidOutput, OutputTruncated
from app.llm.json_output import schema_instruction
from app.llm.roles import Role
from app.llm.types import ChatMessage
from tests.mock_endpoint import MockEndpoint, completion, error
from tests.unit.conftest import LLMFactory

ReadEvents = Callable[[], list[dict[str, Any]]]

MESSAGES = [
    ChatMessage(role="system", content="You are the gate."),
    ChatMessage(role="user", content="What savings accounts do you have?"),
]


class GateVerdict(BaseModel):
    unlocked: list[str]
    products_mentioned: list[str]


GOOD = '{"unlocked": ["f1"], "products_mentioned": []}'
EXPECTED = GateVerdict(unlocked=["f1"], products_mentioned=[])


async def gate(llm: Any, messages: list[ChatMessage] = MESSAGES, **kwargs: Any) -> Any:
    kwargs.setdefault("max_tokens", 200)
    return await llm.chat_json(Role.GATE, messages, GateVerdict, **kwargs)


async def test_schema_mode_sends_response_format_and_validates(
    make_llm: LLMFactory, endpoint: MockEndpoint, read_events: ReadEvents
) -> None:
    endpoint.queue(completion(GOOD))

    value, result = await gate(make_llm(), prompt_version="gate0001")

    assert value == EXPECTED
    assert (result.json_mode, result.attempts, result.text) == ("schema", 1, GOOD)
    body = endpoint.chat_bodies[0]
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "GateVerdict", "schema": GateVerdict.model_json_schema()},
    }
    assert body["temperature"] == 0
    assert body["messages"] == [m.model_dump() for m in MESSAGES]
    event = read_events()[0]
    assert (event["json_mode"], event["outcome"], event["prompt_version"]) == (
        "schema",
        "ok",
        "gate0001",
    )


async def test_rejected_response_format_switches_to_prompt_mode_and_is_remembered(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(
        error(400, "response_format `json_schema` is not supported with this model"),
        completion(GOOD),
        completion(GOOD),
    )
    llm = make_llm()

    first_value, first = await gate(llm)
    _, second = await gate(llm)

    assert first_value == EXPECTED
    assert (first.json_mode, first.attempts) == ("prompt", 2)
    assert (second.json_mode, second.attempts) == ("prompt", 1)
    retry = endpoint.chat_bodies[1]
    assert "response_format" not in retry
    system = retry["messages"][0]
    assert system["role"] == "system"
    assert system["content"] == f"You are the gate.\n\n{schema_instruction(GateVerdict)}"
    assert retry["messages"][1:] == [MESSAGES[1].model_dump()]
    assert "response_format" not in endpoint.chat_bodies[2]


async def test_prompt_mode_adds_a_system_message_when_there_is_none(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(error(400, "Invalid parameter: response_format"), completion(GOOD))

    await gate(make_llm(), [ChatMessage(role="user", content="hi")])

    assert endpoint.chat_bodies[1]["messages"] == [
        {"role": "system", "content": schema_instruction(GateVerdict)},
        {"role": "user", "content": "hi"},
    ]


async def test_both_parameters_rejected_takes_three_attempts(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(
        error(400, "unknown field: reasoning_effort"),
        error(400, "json_schema response format is not supported"),
        completion(GOOD),
    )

    value, result = await gate(make_llm())

    assert value == EXPECTED
    assert (result.json_mode, result.attempts) == ("prompt", 3)
    assert result.json_retried is False  # dropped parameters, not a second try at the JSON
    last = endpoint.chat_bodies[2]
    assert "reasoning_effort" not in last
    assert "response_format" not in last


async def test_invalid_json_then_valid_json_succeeds_in_two_attempts(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(completion("Sure! The student asked about f1."), completion(GOOD))

    value, result = await gate(make_llm())

    assert value == EXPECTED
    assert (result.attempts, result.json_retried) == (2, True)
    first, retry = endpoint.chat_bodies
    assert retry["messages"][:-1] == first["messages"]
    nudge = retry["messages"][-1]
    assert nudge["role"] == "user"
    assert "no JSON object" in nudge["content"]
    assert nudge["content"].endswith("Return only valid JSON.")
    assert retry["max_tokens"] == 200


async def test_json_that_fails_validation_is_retried_with_the_problem(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(completion('{"unlocked": "f1"}'), completion(GOOD))

    _, result = await gate(make_llm())

    assert result.attempts == 2
    assert "does not match the schema" in endpoint.chat_bodies[1]["messages"][-1]["content"]


async def test_invalid_json_twice_raises_invalid_output(
    make_llm: LLMFactory, endpoint: MockEndpoint, read_events: ReadEvents
) -> None:
    endpoint.queue(completion("not json " * 100), completion("still not json"))

    with pytest.raises(InvalidOutput) as info:
        await gate(make_llm())

    assert not isinstance(info.value, OutputTruncated)
    assert info.value.raw_text == "still not json"
    event = read_events()[-1]
    assert (event["outcome"], event["attempts"]) == ("INVALID_OUTPUT", 2)


async def test_raw_text_on_the_error_is_capped_at_500_chars(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(completion("x" * 900), completion("y" * 900))
    with pytest.raises(InvalidOutput) as info:
        await gate(make_llm())
    assert info.value.raw_text == "y" * 500


async def test_empty_reply_cut_off_is_retried_with_max_tokens_doubled(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(completion("", finish_reason="length"), completion(GOOD))

    value, result = await gate(make_llm(), max_tokens=300)

    assert value == EXPECTED
    assert (result.attempts, result.json_retried) == (2, True)
    first, retry = endpoint.chat_bodies
    assert [first["max_tokens"], retry["max_tokens"]] == [300, 600]
    assert retry["messages"] == first["messages"]  # more room, not a nudge


async def test_json_cut_off_midway_is_also_retried_with_max_tokens_doubled(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(completion('{"unlocked": ["f1", "f', finish_reason="length"), completion(GOOD))

    _, result = await gate(make_llm(), max_tokens=300)

    assert result.attempts == 2
    assert [b["max_tokens"] for b in endpoint.chat_bodies] == [300, 600]


async def test_cut_off_twice_raises_invalid_output_recorded_as_truncated(
    make_llm: LLMFactory, endpoint: MockEndpoint, read_events: ReadEvents
) -> None:
    endpoint.queue(
        completion("", finish_reason="length"),
        completion("<think>still thinking", finish_reason="length"),
    )

    with pytest.raises(InvalidOutput) as info:
        await gate(make_llm())

    assert isinstance(info.value, OutputTruncated)
    event = read_events()[-1]
    assert (event["outcome"], event["attempts"]) == ("truncated", 2)


async def test_groq_json_validate_failed_counts_as_invalid_json(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(
        error(400, "Failed to generate JSON. Adjust your prompt.", code="json_validate_failed"),
        completion(GOOD),
    )

    value, result = await gate(make_llm())

    assert value == EXPECTED
    assert (result.json_mode, result.attempts) == ("schema", 2)
    retry = endpoint.chat_bodies[1]
    assert retry["response_format"]["type"] == "json_schema"
    assert retry["messages"][-1]["content"].endswith("Return only valid JSON.")


async def test_reasoning_and_fences_around_the_json_are_ignored(
    make_llm: LLMFactory, endpoint: MockEndpoint
) -> None:
    endpoint.queue(completion(f"<think>which facts?</think>\n```json\n{GOOD}\n```"))
    value, result = await gate(make_llm())
    assert value == EXPECTED
    assert result.attempts == 1
