import pytest
from pydantic import BaseModel

from app.llm.errors import InvalidOutput, ModelTimeout, ModelUnavailable
from app.llm.fake import FAKE_MODEL, FakeLLM
from app.llm.roles import Role
from app.llm.types import ChatMessage

MESSAGES = [ChatMessage(role="user", content="Hello?")]


class Verdict(BaseModel):
    unlocked: list[str]


async def test_replies_come_from_each_roles_queue_in_order() -> None:
    llm = FakeLLM({Role.CLIENT: ["first", "second"], Role.GATE: ['{"unlocked": []}']})

    first = await llm.chat(Role.CLIENT, MESSAGES, max_tokens=50, temperature=0.7)
    second = await llm.chat(Role.CLIENT, MESSAGES, max_tokens=50, temperature=0.7)

    assert (first.text, second.text) == ("first", "second")
    assert first.model == FAKE_MODEL
    assert first.role is Role.CLIENT
    assert (first.attempts, first.json_mode, first.cached) == (1, "none", False)


async def test_every_call_is_recorded() -> None:
    llm = FakeLLM({Role.COACH: ["fine"]})

    await llm.chat(
        Role.COACH, MESSAGES, model="big", max_tokens=99, temperature=0.3, prompt_version="v2"
    )

    (call,) = llm.calls
    assert (call.method, call.role, call.model) == ("chat", Role.COACH, "big")
    assert call.messages == tuple(MESSAGES)
    assert (call.max_tokens, call.temperature, call.prompt_version) == (99, 0.3, "v2")
    assert llm.calls_for(Role.COACH) == [call]
    assert llm.calls_for(Role.GATE) == []


async def test_scripted_errors_are_raised() -> None:
    llm = FakeLLM()
    llm.script(Role.CLIENT, ModelTimeout("slow"), "recovered")

    with pytest.raises(ModelTimeout):
        await llm.chat(Role.CLIENT, MESSAGES, max_tokens=50, temperature=0.7)
    result = await llm.chat(Role.CLIENT, MESSAGES, max_tokens=50, temperature=0.7)
    assert result.text == "recovered"


async def test_chat_json_accepts_models_mappings_and_text() -> None:
    llm = FakeLLM(
        {Role.GATE: [Verdict(unlocked=["a"]), {"unlocked": ["b"]}, '```json\n{"unlocked": []}```']}
    )

    values = [
        (await llm.chat_json(Role.GATE, MESSAGES, Verdict, max_tokens=200))[0] for _ in range(3)
    ]

    assert values == [Verdict(unlocked=["a"]), Verdict(unlocked=["b"]), Verdict(unlocked=[])]
    assert llm.calls[0].schema is Verdict
    assert llm.calls[0].method == "chat_json"


async def test_chat_json_with_bad_json_raises_invalid_output() -> None:
    llm = FakeLLM({Role.GATE: ["not json"]})
    with pytest.raises(InvalidOutput):
        await llm.chat_json(Role.GATE, MESSAGES, Verdict, max_tokens=200)


async def test_running_out_of_script_fails_loudly() -> None:
    llm = FakeLLM()
    with pytest.raises(AssertionError, match="'gate'"):
        await llm.chat(Role.GATE, MESSAGES, max_tokens=50, temperature=0)


async def test_list_models_returns_models_or_raises() -> None:
    assert await FakeLLM(models=["a", "b"]).list_models() == ["a", "b"]
    down = FakeLLM(list_models_error=ModelUnavailable("down"))
    with pytest.raises(ModelUnavailable):
        await down.list_models()
    assert down.list_models_calls == 1
