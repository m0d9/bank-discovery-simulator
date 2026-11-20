import pytest

from app.llm import ChatMessage, InvalidOutput, ModelTimeout, OutputTruncated, Role
from app.llm.fake import FakeLLM, Scripted
from app.prompts import PROMPT_VERSION
from app.simulation.client_agent import (
    FALLBACK_LINES,
    ClientReply,
    LanguageRetry,
    client_history,
    client_language_reminder,
    client_reminder,
    client_system_prompt,
    generate_reply,
    language_mismatch,
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


async def reply_with(
    *scripted: Scripted, language: Language = "en", history: list[ChatMessage] = HISTORY
) -> tuple[ClientReply, FakeLLM]:
    fake = FakeLLM(script={Role.CLIENT: scripted})
    reply = await generate_reply(
        fake,
        model="client-model",
        system_prompt=SYSTEM,
        reminder=REMINDER,
        history=history,
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


# The manual test: five questions in a numbered list, in English, got a reply in Arabic.
NUMBERED = [
    ChatMessage(
        role="user",
        content="1. How quickly do your corporate clients pay your invoices?\n"
        "2. How long has the company been trading?\n3. When do you pay salaries each month?",
    )
]
ARABIC = [ChatMessage(role="user", content="كيف يدفع لك عملاؤك عادةً؟")]
LANGUAGE_VERSION = f"{PROMPT_VERSION['client_system']}+{PROMPT_VERSION['client_language']}"


@pytest.mark.parametrize(
    ("student", "reply", "expected"),
    [
        ("How do your customers pay you?", "They pay late, sometimes.", None),
        ("كيف يدفعون؟", "يدفعون بعد 90 يومًا، أي نحو 350,000 ريال قطري.", None),
        ("How do your customers pay you?", "يدفعون متأخرين أحيانًا.", "script"),
        ("كيف يدفعون؟", "They pay late, sometimes.", "script"),
        ("كيف يدفعون؟", "يدفعون متأخرين lately.", "latin_word"),
        # Most letters decide the script, and a single Latin letter isn't a word.
        ("Does Noura (نورة) need cash?", "Yes, she does.", None),
        ("كيف يدفعون؟", "الخطة A جاهزة.", None),
        # A message with no letters sets no script; only a Latin word in Arabic counts then.
        ("?", "يدفعون متأخرين.", None),
        ("?", "They pay late.", None),
    ],
)
def test_a_reply_in_the_wrong_language_is_recognised(
    student: str, reply: str, expected: str | None
) -> None:
    assert language_mismatch(student, reply) == expected


async def test_a_reply_in_the_other_script_is_regenerated_with_the_language_reminder() -> None:
    reply, fake = await reply_with(
        "يدفعون خلال 60 إلى 90 يومًا.", "They pay in 60 to 90 days.", history=NUMBERED
    )

    assert reply.text == "They pay in 60 to 90 days."
    assert reply.language_retry == LanguageRetry(
        reason="script", retried=True, fixed=True, first_text="يدفعون خلال 60 إلى 90 يومًا."
    )
    assert (reply.role_break, reply.regenerated, reply.attempts) == (False, False, 2)
    first, second = fake.calls
    assert second.messages[0].content == f"{SYSTEM}\n\n{client_language_reminder('en')}"
    assert second.messages[1:] == first.messages[1:]
    assert second.prompt_version == LANGUAGE_VERSION


async def test_an_english_reply_to_an_arabic_message_is_regenerated_in_arabic() -> None:
    reply, fake = await reply_with("They pay late.", "يدفعون متأخرين.", history=ARABIC)

    assert reply.text == "يدفعون متأخرين."
    assert reply.language_retry is not None and reply.language_retry.fixed
    assert fake.calls[1].messages[0].content == f"{SYSTEM}\n\n{client_language_reminder('ar')}"


async def test_a_latin_word_in_an_arabic_reply_is_regenerated_in_arabic() -> None:
    reply, fake = await reply_with(
        "يتأخرون في الدفع lately.", "يتأخرون في الدفع مؤخرًا.", history=ARABIC
    )

    assert reply.text == "يتأخرون في الدفع مؤخرًا."
    assert reply.language_retry == LanguageRetry(
        reason="latin_word", retried=True, fixed=True, first_text="يتأخرون في الدفع lately."
    )
    assert fake.calls[1].messages[0].content == f"{SYSTEM}\n\n{client_language_reminder('ar')}"


@pytest.mark.parametrize(
    ("history", "text"),
    [(HISTORY, "They pay late, sometimes."), (ARABIC, "يدفعون بعد 90 يومًا تقريبًا.")],
)
async def test_a_reply_in_the_right_language_takes_one_call(
    history: list[ChatMessage], text: str
) -> None:
    reply, fake = await reply_with(text, history=history)

    assert (reply.text, reply.language_retry) == (text, None)
    assert len(fake.calls) == 1


async def test_a_retry_still_in_the_wrong_language_is_kept() -> None:
    reply, _ = await reply_with("يدفعون متأخرين.", "ما زالوا يتأخرون.", history=NUMBERED)

    assert reply.text == "ما زالوا يتأخرون."
    assert reply.language_retry == LanguageRetry(
        reason="script", retried=True, fixed=False, first_text="يدفعون متأخرين."
    )


@pytest.mark.parametrize(
    "second", ["", OutputTruncated("all reasoning"), "As an AI, I can't say.", ModelTimeout("slow")]
)
async def test_an_unusable_retry_keeps_the_first_reply_and_never_fails_the_turn(
    second: Scripted,
) -> None:
    reply, _ = await reply_with("يدفعون متأخرين.", second, history=NUMBERED)

    assert reply.text == "يدفعون متأخرين."
    assert reply.language_retry == LanguageRetry(
        reason="script", retried=False, fixed=False, first_text="يدفعون متأخرين."
    )
    assert not reply.role_break and reply.attempts == 2


async def test_the_fallback_line_is_not_checked_for_language() -> None:
    reply, fake = await reply_with(
        "As an AI, I can't say.", "I am a language model.", language="ar"
    )

    assert reply.text == FALLBACK_LINES["ar"] and reply.language_retry is None
    assert len(fake.calls) == 2


async def test_a_reply_regenerated_for_character_is_then_checked_for_language() -> None:
    reply, fake = await reply_with(
        "As an AI, I can't say.", "يدفعون متأخرين.", "They pay late.", history=NUMBERED
    )

    assert (reply.text, reply.regenerated, reply.attempts) == ("They pay late.", True, 3)
    assert reply.language_retry is not None and reply.language_retry.fixed
    assert [call.prompt_version for call in fake.calls][1:] == [
        f"{PROMPT_VERSION['client_system']}+{PROMPT_VERSION['client_reminder']}",
        LANGUAGE_VERSION,
    ]
