"""The AI client: its system prompt, the history it sees, and checks on what it says."""

import re
import time
import unicodedata
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from app.content import Bank, Client, Product
from app.llm import ChatMessage, InvalidOutput, LLMClient, OutputTruncated, Role
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


def client_history(turns: Sequence[Turn], limit: int) -> list[ChatMessage]:
    """The last `limit` turns as chat messages: the student is the user, the client the
    assistant."""
    return [
        ChatMessage(role="user" if turn.role == "student" else "assistant", content=turn.text)
        for turn in turns[-limit:]
    ]


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

    def reply(text: str, *, role_break: bool, regenerated: bool) -> ClientReply:
        elapsed = round((time.perf_counter() - started) * 1000)
        return ClientReply(text, role_break, regenerated, attempts, elapsed)

    version = PROMPT_VERSION["client_system"]
    text = await ask(system_prompt, version) or await ask(system_prompt, version)
    if not text:
        raise InvalidOutput("the client model returned an empty reply twice")
    if not breaks_character(text):
        return reply(text, role_break=False, regenerated=False)
    # Appended to the one system message: a second system message confuses some chat templates.
    retry = await ask(
        f"{system_prompt}\n\n{reminder}", f"{version}+{PROMPT_VERSION['client_reminder']}"
    )
    if retry and not breaks_character(retry):
        return reply(retry, role_break=False, regenerated=True)
    return reply(FALLBACK_LINES[language], role_break=True, regenerated=True)


def _bullets(items: Iterable[str]) -> str:
    lines = [f"- {item}" for item in items]
    return "\n".join(lines) if lines else f"- {NOTHING_LISTED}"
