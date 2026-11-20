import pytest

from app.llm import ChatMessage, InvalidOutput, ModelTimeout, OutputTruncated, Role
from app.llm.fake import FakeLLM, Scripted
from app.prompts import PROMPT_VERSION
from app.simulation.client_agent import (
    FALLBACK_LINES,
    ClientReply,
    client_history,
    client_reminder,
    client_system_prompt,
    generate_reply,
)
from app.simulation.models import Language, Turn
from tests.interview_factory import T0, client_with, hidden_fact, registry

CONTENT = registry()
BANK = CONTENT.bank
PRODUCTS = CONTENT.list_products()
CLIENT = client_with(
    hidden_fact("cash-gap", signal="SIGNAL-CASH-GAP"),
    hidden_fact("expansion", importance="important", requires=["cash-gap"], signal="SIGNAL-EXP"),
)
SYSTEM = "SYSTEM PROMPT"
REMINDER = "STAY IN CHARACTER"
HISTORY = [ChatMessage(role="user", content="How do your customers pay you?")]


def test_the_system_prompt_describes_the_client_and_lists_nothing_private_yet() -> None:
    prompt = client_system_prompt(CLIENT, BANK, PRODUCTS, unlocked=set())

    assert "You are Test Client" in prompt and "(in Arabic: عميل الاختبار)" in prompt
    assert "Test Bank" in prompt and "(in Arabic: بنك الاختبار)" in prompt
    assert "Runs a small company in Doha." in prompt and "Runs a company in Doha." in prompt
    assert "Family: (not stated)" in prompt
    assert "- Alpha Loan: A business loan that charges interest." in prompt
    for fact in CLIENT.hidden_facts:
        assert fact.content not in prompt
    assert "SIGNAL-CASH-GAP" in prompt  # eligible and locked: a hint
    assert "SIGNAL-EXP" not in prompt  # not eligible until cash-gap unlocks
    assert "$" not in prompt


def test_unlocking_a_fact_shares_its_content_and_turns_the_next_signal_on() -> None:
    prompt = client_system_prompt(CLIENT, BANK, PRODUCTS, unlocked={"cash-gap"})

    assert CLIENT.hidden_facts[0].content in prompt
    assert CLIENT.hidden_facts[1].content not in prompt
    assert "SIGNAL-CASH-GAP" not in prompt  # no hint for a fact that's already shared
    assert "SIGNAL-EXP" in prompt


def test_the_reminder_names_the_client_and_the_bank() -> None:
    reminder = client_reminder(CLIENT, BANK)
    assert "Test Client" in reminder and "Test Bank" in reminder


def test_history_is_the_last_turns_with_the_student_as_the_user() -> None:
    turns = [
        Turn(n=n, role="client" if n % 2 == 0 else "student", text=f"t{n}", ts=T0) for n in range(6)
    ]

    history = client_history(turns, limit=3)

    assert [(m.role, m.content) for m in history] == [
        ("user", "t3"),
        ("assistant", "t4"),
        ("user", "t5"),
    ]


async def reply_with(*scripted: Scripted, language: Language = "en") -> tuple[ClientReply, FakeLLM]:
    fake = FakeLLM(script={Role.CLIENT: scripted})
    reply = await generate_reply(
        fake,
        model="client-model",
        system_prompt=SYSTEM,
        reminder=REMINDER,
        history=HISTORY,
        language=language,
    )
    return reply, fake


async def test_a_good_reply_takes_one_call_with_the_spec_parameters() -> None:
    reply, fake = await reply_with("  They pay late, sometimes.  ")

    assert reply == ClientReply("They pay late, sometimes.", False, False, 1, reply.latency_ms)
    [call] = fake.calls
    assert (call.method, call.role, call.model) == ("chat", Role.CLIENT, "client-model")
    assert (call.temperature, call.max_tokens) == (0.7, 250)
    assert call.prompt_version == PROMPT_VERSION["client_system"]
    assert call.messages == (ChatMessage(role="system", content=SYSTEM), *HISTORY)


@pytest.mark.parametrize("first", ["", "   ", OutputTruncated("all reasoning")])
async def test_an_empty_reply_is_retried_once(first: Scripted) -> None:
    reply, fake = await reply_with(first, "They pay late.")

    assert reply.text == "They pay late." and reply.attempts == 2
    assert len(fake.calls) == 2


async def test_an_empty_reply_twice_is_invalid_output() -> None:
    with pytest.raises(InvalidOutput, match="empty reply twice"):
        await reply_with("", "")


async def test_a_character_break_is_regenerated_with_the_reminder() -> None:
    reply, fake = await reply_with("As an AI, I can't say.", "They pay late.")

    assert (reply.text, reply.role_break, reply.regenerated) == ("They pay late.", False, True)
    first, second = fake.calls
    assert first.messages[0].content == SYSTEM
    assert second.messages[0].content == f"{SYSTEM}\n\n{REMINDER}"
    assert second.messages[1:] == first.messages[1:]
    expected = f"{PROMPT_VERSION['client_system']}+{PROMPT_VERSION['client_reminder']}"
    assert second.prompt_version == expected


@pytest.mark.parametrize("language", ["en", "ar"])
@pytest.mark.parametrize("second", ["I am a language model.", "", OutputTruncated("x")])
async def test_a_second_break_uses_the_fallback_line(language: Language, second: Scripted) -> None:
    reply, _ = await reply_with("As an AI, I can't say.", second, language=language)

    assert reply.text == FALLBACK_LINES[language]
    assert reply.role_break and reply.regenerated and reply.attempts == 2


def test_the_fallback_lines() -> None:
    assert FALLBACK_LINES == {
        "en": "Sorry, could you put that another way?",
        "ar": "عذرًا، هل يمكنك إعادة صياغة كلامك؟",
    }


async def test_other_model_errors_propagate() -> None:
    with pytest.raises(ModelTimeout):
        await reply_with(ModelTimeout("slow"))
