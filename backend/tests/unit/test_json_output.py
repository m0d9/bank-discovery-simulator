import json

import pytest
from pydantic import BaseModel

from app.llm.errors import InvalidOutput, ModelUnavailable, OutputTruncated, outcome_of
from app.llm.json_output import (
    extract_json,
    json_retry_instruction,
    parse_reply,
    schema_instruction,
    strip_reasoning,
)


class Verdict(BaseModel):
    unlocked: list[str]
    confident: bool


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Hello there.", "Hello there."),
        ("<think>plan the reply</think>Hello.", "Hello."),
        ("<think>\nline one\nline two\n</think>\n\nHello.", "Hello."),
        ("<THINK>shouting</THINK> Hi", "Hi"),
        ("<thinking>a</thinking>Hi<think>b</think> there", "Hi there"),
        ("reasoning the template opened\n</think>\nHello.", "Hello."),
        ("Hello.<think>the reply was cut off mid-thought", "Hello."),
        ("<think>never finished", ""),
    ],
)
def test_strip_reasoning(raw: str, expected: str) -> None:
    assert strip_reasoning(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        '```\n{"a": 1}```',
        'Sure! Here it is: {"a": 1} Hope that helps.',
        'Not this {broken, but this: {"a": 1}',
        '{"a": 1} {"b": 2}',
    ],
)
def test_extract_json_finds_the_first_object(raw: str) -> None:
    assert extract_json(raw) == {"a": 1}


def test_extract_json_keeps_nested_objects() -> None:
    assert extract_json('{"outer": {"inner": [1, 2]}}') == {"outer": {"inner": [1, 2]}}


@pytest.mark.parametrize("raw", ["", "no json here", "[1, 2, 3]", '{"unterminated": '])
def test_extract_json_raises_without_an_object(raw: str) -> None:
    with pytest.raises(ValueError, match="no JSON object"):
        extract_json(raw)


def test_parse_reply_validates_against_the_schema() -> None:
    verdict = parse_reply('{"unlocked": ["f1"], "confident": true}', Verdict)
    assert verdict == Verdict(unlocked=["f1"], confident=True)


def test_parse_reply_reports_schema_problems_without_echoing_input() -> None:
    with pytest.raises(ValueError) as info:
        parse_reply('{"unlocked": "SECRET-INPUT"}', Verdict)
    message = str(info.value)
    assert "does not match the schema" in message
    assert "confident" in message
    assert "SECRET-INPUT" not in message
    assert len(message) <= 300


def test_schema_instruction_is_compact_and_names_the_fields() -> None:
    instruction = schema_instruction(Verdict)
    assert "\n" not in instruction
    assert "JSON" in instruction
    schema_part = instruction[instruction.index("{") :]
    assert json.loads(schema_part) == Verdict.model_json_schema()


def test_retry_instruction_includes_the_problem() -> None:
    message = json_retry_instruction("the reply contains no JSON object")
    assert "no JSON object" in message
    assert message.endswith("Return only valid JSON.")


def test_invalid_output_keeps_at_most_500_chars_and_hides_them_from_str() -> None:
    error = InvalidOutput("bad json", raw_text="x" * 2000)
    assert len(error.raw_text) == 500
    assert str(error) == "bad json"


def test_outcome_of_maps_truncation_and_codes() -> None:
    assert outcome_of(OutputTruncated("cut off")) == "truncated"
    assert outcome_of(InvalidOutput("bad")) == "INVALID_OUTPUT"
    assert outcome_of(ModelUnavailable("down")) == "MODEL_UNAVAILABLE"
    assert isinstance(OutputTruncated(), InvalidOutput)
