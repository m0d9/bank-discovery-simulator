"""Smoke tests against the real endpoint in `.env`. Run with `make test-live`."""

import pytest

from app.config import get_settings
from app.llm import Role
from app.llm.client import OpenAICompatClient
from app.llm.smoke import (
    SMOKE_PROMPT_VERSION,
    TINY_MAX_TOKENS,
    TINY_PROMPT,
    run_long_prompt_check,
    thinking_leaked,
)

pytestmark = pytest.mark.live


def _client() -> OpenAICompatClient:
    # A fresh client per test: each test runs on its own event loop.
    return OpenAICompatClient(get_settings())


@pytest.mark.parametrize("role", list(Role))
async def test_each_role_answers_without_thinking_text(role: Role) -> None:
    result = await _client().chat(
        role,
        TINY_PROMPT,
        max_tokens=TINY_MAX_TOKENS,
        temperature=0,
        prompt_version=SMOKE_PROMPT_VERSION,
    )
    assert result.text.strip()
    assert not thinking_leaked(result.text)


async def test_the_coach_sees_the_whole_long_prompt() -> None:
    check, _ = await run_long_prompt_check(_client())
    assert check.passed, check
