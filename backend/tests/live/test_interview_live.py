"""Scripted Noura interviews against the real model in `.env`. Run with `make test-live`.

The replies are sampled (temperature 0.7), so a failure here is a finding to report, not a
test to loosen.
"""

import re

import pytest

from app.config import get_settings
from app.content import load_registry
from app.llm.client import OpenAICompatClient
from app.simulation import InterviewService, SessionStore
from app.telemetry.events import event_logger_for

pytestmark = pytest.mark.live

NOURA = "noura-al-kuwari"
GENERIC = (
    "Thanks for coming in. Could you tell me a bit about your business?",
    "How is business going at the moment?",
    "What brings you in today?",
    "Is there anything else I should know?",
)
PREFERENCE_QUESTION = "Do you have any preference for Islamic banking?"
OVERDRAFT_PITCH = (
    "I'd suggest our Business Overdraft: a flexible credit limit on your business account, "
    "and you only pay interest on what you use."
)
# A volunteered preference: Islam, Sharia, halal, riba, or interest-based / interest-free.
PREFERENCE_WORDS = re.compile(r"islam|shari|halal|\briba\b|interest[- ]?(?:based|free)", re.I)


def service() -> InterviewService:
    # A fresh client per test: each test runs on its own event loop.
    settings = get_settings()
    return InterviewService(
        store=SessionStore.from_settings(settings),
        llm=OpenAICompatClient(settings),
        settings=settings,
        events=event_logger_for(settings.DATA_DIR),
        content=load_registry(settings.CONTENT_DIR),
    )


async def test_generic_questions_do_not_unlock_sharia_only_but_asking_does() -> None:
    interview = service()
    session = await interview.create_session(NOURA, "en")

    for question in GENERIC[:3]:
        result = await interview.student_message(session.id, question)
        assert "sharia-only" not in session.unlocked, (question, result.gate_note)

    result = await interview.student_message(session.id, PREFERENCE_QUESTION)
    assert "sharia-only" in result.unlocked_now, result.gate_note


async def test_noura_volunteers_no_islamic_preference_in_four_generic_replies() -> None:
    interview = service()
    session = await interview.create_session(NOURA, "en")

    replies = [
        (await interview.student_message(session.id, question)).client_turn.text
        for question in GENERIC
    ]

    assert "sharia-only" not in session.unlocked
    assert [reply for reply in replies if PREFERENCE_WORDS.search(reply)] == []


async def test_pitching_the_overdraft_unlocks_sharia_only() -> None:
    interview = service()
    session = await interview.create_session(NOURA, "en")

    result = await interview.student_message(session.id, OVERDRAFT_PITCH)

    assert "business-overdraft" in result.products_mentioned, result.gate_note
    assert "sharia-only" in result.unlocked_by_pitch
