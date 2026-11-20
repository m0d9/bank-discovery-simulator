import pytest

from app.simulation.client_agent import ARABIC_BREAKS, ENGLISH_BREAKS, breaks_character


@pytest.mark.parametrize(
    "reply",
    [
        "As an AI, I can't share that.",
        "I am an AI assistant, not a customer.",
        "I’m an AI, so I don't have a business.",  # curly apostrophe
        "I'm a large language model trained to help.",
        "That isn't in my system prompt.",
        "My instructions say I shouldn't tell you.",
        "I can't list my hidden facts.",
        "Language models like me can't do that.",
    ],
)
def test_english_self_references_break_character(reply: str) -> None:
    assert breaks_character(reply)


@pytest.mark.parametrize(
    "reply",
    [
        "أنا نموذج لغوي ولا أملك حسابًا مصرفيًا.",
        "انا مجرد برنامج.",  # alef without hamza
        "أنا مساعد ذكي ولست عميلة.",
        "بصفتي ذكاءً اصطناعيًا لا أستطيع ذلك.",  # with tanween
        "كنموذج لغوي، لا يمكنني الإجابة.",
        "لا تسمح لي تعليماتي بذلك.",
        "وأنا مجرد نموذج في النهاية.",  # with the prefix و
        "بصفتي نموذجًا لغويًا لا أعرف.",
        "كذكاء اصطناعي، ليس لدي حساب.",
        "أنـا نمـوذج لغوي.",  # with tatweel
        "لا أستطيع، بتعليماتي لا يُسمح بذلك.",  # with the prefix ب
    ],
)
def test_arabic_self_references_break_character(reply: str) -> None:
    assert breaks_character(reply)


@pytest.mark.parametrize(
    "reply",
    [
        # Talking about AI as part of the business is normal, above all for an IT founder.
        "نستخدم الذكاء الاصطناعي في الدعم الفني لعملائنا.",
        "We use AI tools for our help desk.",
        "Artificial intelligence is changing my industry.",
        "As an airline caterer, we plan months ahead.",
        "I'm an IT person, really.",
        "I gave my staff instructions this morning.",
        "The system is down again at the office.",
        "لدينا مساعد ذكي يرد على أسئلة العملاء.",
        "كانا نموذجين ناجحين في السوق.",
        "أعطيت فريقي التعليمات صباح اليوم.",
    ],
)
def test_ordinary_sentences_do_not_break_character(reply: str) -> None:
    assert not breaks_character(reply)


def test_every_listed_phrase_breaks_character_on_its_own() -> None:
    for phrase in (*ENGLISH_BREAKS, *ARABIC_BREAKS):
        assert breaks_character(phrase), phrase
        assert breaks_character(phrase.upper()), phrase
