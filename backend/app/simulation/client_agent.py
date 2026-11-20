"""The AI client: its system prompt, the history it sees, and checks on what it says."""

import re
import time
import unicodedata
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from app.content import Bank, Client, Product
from app.llm import ChatMessage, InvalidOutput, LLMClient, LLMError, OutputTruncated, Role
from app.prompts import PROMPT_VERSION, render
from app.simulation.disclosure import eligible_facts
from app.simulation.models import Language, Turn

CLIENT_MAX_TOKENS = 250
CLIENT_TEMPERATURE = 0.7
NOTHING_LISTED = "(none)"
NOT_STATED = "(not stated)"

FALLBACK_LINES: Mapping[Language, str] = MappingProxyType(
    {
        "en": "Sorry, could you put that another way?",
        "ar": "عذرًا، هل يمكنك إعادة صياغة كلامك؟",
    }
)
"""What the client says when it can't stay in character, in the session's language."""

# Only phrases in which the speaker describes itself: a client may talk about AI in passing
# (Rajesh runs an IT company), but a real customer never calls themselves a model.
ENGLISH_BREAKS = (
    "as an ai",
    "i am an ai",
    "i'm an ai",
    "language model",
    "system prompt",
    "my instructions",
    "hidden facts",
)
ARABIC_BREAKS = (
    "أنا نموذج",
    "أنا مجرد نموذج",
    "أنا مجرد برنامج",
    "أنا مساعد ذكي",
    "بصفتي ذكاء اصطناعي",
    "بصفتي نموذج",
    "كذكاء اصطناعي",
    "كنموذج لغوي",
    "تعليماتي",
)

# Harakat, tanween, Quranic marks and tatweel: models add them inconsistently.
_ARABIC_MARKS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_LETTER_FORMS = str.maketrans(
    {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "’": "'", "‘": "'", "ʼ": "'"}
)
_SPACES = re.compile(r"\s+")
# One-letter prefixes that attach to an Arabic word: and, so, with, for.
_ARABIC_PREFIXES = "وفبل"


def normalise(text: str) -> str:
    """Text folded for matching: NFKC, no Arabic diacritics or tatweel, one form of alef, one
    space between words, and case-folded."""
    text = _ARABIC_MARKS.sub("", unicodedata.normalize("NFKC", text))
    return _SPACES.sub(" ", text.translate(_LETTER_FORMS)).casefold()


_ENGLISH_PATTERN = re.compile(r"\b(?:" + "|".join(map(re.escape, ENGLISH_BREAKS)) + r")s?\b")
_ARABIC_PATTERN = re.compile(
    "|".join(
        rf"(?<!\w)[{_ARABIC_PREFIXES}]?{re.escape(normalise(phrase))}" for phrase in ARABIC_BREAKS
    )
)


def breaks_character(text: str) -> bool:
    """True if the reply speaks of itself as an AI, a model or a prompt.

    English phrases match whole words, case-insensitively ("as an ai" doesn't match "as an
    airline"). Arabic phrases match at the start of a word, with or without a prefix such as
    و, after removing diacritics and unifying the forms of alef.
    """
    normalised = normalise(text)
    return bool(_ENGLISH_PATTERN.search(normalised) or _ARABIC_PATTERN.search(normalised))


def client_system_prompt(
    client: Client, bank: Bank, products: Sequence[Product], *, unlocked: Collection[str]
) -> str:
    """The client's system prompt: who they are, what they may share or hint at, how to behave.

    `unlocked` holds every fact unlocked so far, this turn's included. A locked fact's content
    never appears. Only facts that are eligible (every `requires` unlocked) but still locked
    contribute their signal as a hint.
    """
    persona = client.persona
    shared = [fact.content for fact in client.hidden_facts if fact.id in unlocked]
    hints = [fact.signal for fact in eligible_facts(client, unlocked) if fact.signal]
    catalogue = [
        f"{product.name.en} ({product.name.ar}): {product.client_view}"
        if product.name.ar
        else f"{product.name.en}: {product.client_view}"
        for product in products
    ]
    return render(
        "client_system",
        name=client.card.name.en,
        name_ar=client.card.name.ar or client.card.name.en,
        bank=bank.name.en,
        bank_ar=bank.name.ar or bank.name.en,
        age=persona.age,
        occupation=persona.occupation,
        nationality=persona.nationality,
        family=persona.family or NOT_STATED,
        background=persona.background,
        personality=persona.personality,
        speaking_style=persona.speaking_style,
        financial_knowledge=persona.financial_knowledge,
        open_facts=_bullets(client.open_facts),
        shared_facts=_bullets(shared),
        hints=_bullets(hints),
        products=_bullets(catalogue),
    )


def client_reminder(client: Client, bank: Bank) -> str:
    """The extra instruction for regenerating a reply that broke character."""
    return render("client_reminder", name=client.card.name.en, bank=bank.name.en)


_LANGUAGE_NAMES: Mapping[Language, str] = MappingProxyType({"en": "English", "ar": "Arabic"})


def client_language_reminder(language: Language) -> str:
    """The extra instruction for regenerating a reply that is in the wrong language."""
    return render("client_language", language=_LANGUAGE_NAMES[language])


LanguageMismatch = Literal["script", "latin_word"]

_ARABIC_LETTER = re.compile("[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]")
_LATIN_LETTER = re.compile("[A-Za-z\u00c0-\u024f]")
_LATIN_WORD = re.compile("[A-Za-z\u00c0-\u024f]{2,}")


def script_of(text: str) -> Language | None:
    """The script most of the text's letters are in: "ar" for Arabic letters, "en" for Latin
    letters, or None when it has neither (only digits or punctuation) or as many of each."""
    arabic = latin = 0
    for char in text:
        if not char.isalpha():
            continue
        if _ARABIC_LETTER.match(char):
            arabic += 1
        elif _LATIN_LETTER.match(char):
            latin += 1
    if arabic == latin:
        return None
    return "ar" if arabic > latin else "en"


def language_mismatch(student_message: str, reply: str) -> LanguageMismatch | None:
    """Why `reply` is in the wrong language for the student's message, or None if it isn't.

    "script": the reply is mostly in the other script (Arabic letters against Latin letters).
    "latin_word": the reply is Arabic but has a word of two or more Latin letters in it.
    """
    expected, actual = script_of(student_message), script_of(reply)
    if expected is not None and actual is not None and expected != actual:
        return "script"
    if actual == "ar" and _LATIN_WORD.search(reply):
        return "latin_word"
    return None


def client_history(turns: Sequence[Turn], limit: int) -> list[ChatMessage]:
    """The last `limit` turns as chat messages: the student is the user, the client the
    assistant."""
    return [
        ChatMessage(role="user" if turn.role == "student" else "assistant", content=turn.text)
        for turn in turns[-limit:]
    ]


@dataclass(frozen=True)
class LanguageRetry:
    """A reply in the wrong language, regenerated once with the language reminder."""

    reason: LanguageMismatch
    retried: bool
    """The retry gave a usable reply, which replaced the first. False when the retry was empty,
    broke character or failed: the first reply was kept, so the turn never fails over this."""
    fixed: bool
    """The reply that was kept is in the right language."""
    first_text: str
    """The reply in the wrong language."""


@dataclass(frozen=True)
class ClientReply:
    """The client's checked reply to one student message."""

    text: str
    role_break: bool
    """The reply broke character twice, so the fallback line was used."""
    regenerated: bool
    """The first reply broke character and was regenerated."""
    attempts: int
    latency_ms: int
    language_retry: LanguageRetry | None = None
    """Set when the reply was in the wrong language and was regenerated for that."""


async def generate_reply(
    llm: LLMClient,
    *,
    model: str,
    system_prompt: str,
    reminder: str,
    history: Sequence[ChatMessage],
    language: Language,
) -> ClientReply:
    """Ask the client model for its reply, then check it.

    An empty reply is retried once, and raises `InvalidOutput` if it's empty again. A reply that
    breaks character is regenerated once, with `reminder` added to the system prompt; if that
    breaks character too, or is empty, the fallback line is used. Any other model error
    propagates, so the caller saves nothing for the turn.

    Then the language: a reply in another script than the student's last message, or an Arabic
    reply with a Latin word in it, is regenerated once with the language reminder. The retry's
    reply is kept even if it's still wrong; if it's empty, breaks character or fails, the first
    reply is kept. This check never fails the turn, and the fallback line skips it.
    """
    started = time.perf_counter()
    attempts = 0

    async def ask(system: str, prompt_version: str) -> str:
        nonlocal attempts
        attempts += 1
        messages = [ChatMessage(role="system", content=system), *history]
        try:
            result = await llm.chat(
                Role.CLIENT,
                messages,
                model=model,
                max_tokens=CLIENT_MAX_TOKENS,
                temperature=CLIENT_TEMPERATURE,
                prompt_version=prompt_version,
            )
        except OutputTruncated:
            return ""  # all of max_tokens went on hidden reasoning: no visible reply
        return result.text.strip()

    def reply(
        text: str,
        *,
        role_break: bool,
        regenerated: bool,
        language_retry: LanguageRetry | None = None,
    ) -> ClientReply:
        elapsed = round((time.perf_counter() - started) * 1000)
        return ClientReply(text, role_break, regenerated, attempts, elapsed, language_retry)

    version = PROMPT_VERSION["client_system"]
    text = await ask(system_prompt, version) or await ask(system_prompt, version)
    if not text:
        raise InvalidOutput("the client model returned an empty reply twice")
    regenerated = False
    if breaks_character(text):
        # Appended to the one system message: a second system message confuses some chat
        # templates.
        retry = await ask(
            f"{system_prompt}\n\n{reminder}", f"{version}+{PROMPT_VERSION['client_reminder']}"
        )
        if not retry or breaks_character(retry):
            return reply(FALLBACK_LINES[language], role_break=True, regenerated=True)
        text, regenerated = retry, True

    student = next((message.content for message in reversed(history) if message.role == "user"), "")
    mismatch = language_mismatch(student, text)
    if mismatch is None:
        return reply(text, role_break=False, regenerated=regenerated)
    expected = script_of(student)
    # A Latin word is only a mistake in Arabic; otherwise the reply should match the student.
    target: Language = expected if mismatch == "script" and expected is not None else "ar"
    try:
        retry = await ask(
            f"{system_prompt}\n\n{client_language_reminder(target)}",
            f"{version}+{PROMPT_VERSION['client_language']}",
        )
    except LLMError:
        retry = ""  # the first reply is still a reply: never fail the turn over its language
    usable = bool(retry) and not breaks_character(retry)
    kept = retry if usable else text
    checked = LanguageRetry(
        reason=mismatch,
        retried=usable,
        fixed=language_mismatch(student, kept) is None,
        first_text=text,
    )
    return reply(kept, role_break=False, regenerated=regenerated, language_retry=checked)


def _bullets(items: Iterable[str]) -> str:
    lines = [f"- {item}" for item in items]
    return "\n".join(lines) if lines else f"- {NOTHING_LISTED}"
