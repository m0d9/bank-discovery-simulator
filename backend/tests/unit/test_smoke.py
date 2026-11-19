import re
from collections.abc import Iterator

import pytest

from app.llm import LLMResult, ModelUnavailable, Role, smoke
from app.llm.fake import FakeLLM
from app.llm.smoke import LongPromptCheck, build_long_prompt, run, thinking_leaked
from tests.conftest import SettingsFactory


def test_long_prompt_puts_the_codes_on_the_first_and_last_lines() -> None:
    messages, expected = build_long_prompt("AAAA-0001", "ZZZZ-9999")

    system, user = messages
    assert system.role == "system"
    assert system.content.splitlines()[0] == "FIRST CODE: AAAA-0001"
    assert user.content.splitlines()[-1] == "LAST CODE: ZZZZ-9999"
    assert 5500 <= expected <= 6500


def test_random_codes_differ() -> None:
    codes = {smoke.random_code() for _ in range(20)}
    assert len(codes) == 20
    assert all(re.fullmatch(r"[A-Z]{4}-\d{4}", code) for code in codes)


@pytest.mark.parametrize(
    ("prompt_tokens", "first", "last", "passed"),
    [
        (6100, True, True, True),
        (8000, True, True, True),  # tokenizers often need more tokens than the estimate
        (2048, True, True, False),  # cut to Ollama's default window
        (None, True, True, False),  # no usage reported: size can't be confirmed
        (6100, False, True, False),  # the start of the prompt was lost
        (6100, True, False, False),
    ],
)
def test_long_prompt_check_needs_both_codes_and_the_full_size(
    prompt_tokens: int | None, first: bool, last: bool, passed: bool
) -> None:
    check = LongPromptCheck(
        expected_tokens=6000, prompt_tokens=prompt_tokens, first_seen=first, last_seen=last
    )
    assert check.passed is passed


@pytest.mark.parametrize(
    ("text", "leaked"),
    [("ready", False), ("<think>hmm</think>ready", True), ("ready </THINKING>", True)],
)
def test_thinking_leak_detection(text: str, leaked: bool) -> None:
    assert thinking_leaked(text) is leaked


@pytest.fixture
def fixed_codes(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    codes = iter(["FRST-1111", "LAST-2222"])
    monkeypatch.setattr(smoke, "random_code", lambda: next(codes))
    yield


class _ShortPromptLLM(FakeLLM):
    """Reports far fewer prompt tokens than were sent, the way a truncating server does."""

    async def chat(self, *args: object, **kwargs: object) -> LLMResult:  # type: ignore[override]
        result = await super().chat(*args, **kwargs)  # type: ignore[arg-type]
        return result.model_copy(update={"prompt_tokens": 1026})


async def test_run_passes_and_reports_each_role_cold_and_warm(
    settings_factory: SettingsFactory,
    fixed_codes: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    llm = FakeLLM({role: ["ready", "ready"] for role in Role})
    llm.script(Role.COACH, "FIRST=FRST-1111; LAST=LAST-2222")

    code = await run(llm, settings_factory(), list(Role))

    out = capsys.readouterr().out
    assert code == 0
    assert out.count("cold") == 3 and out.count("warm") == 3
    assert "first-line code: seen | last-line code: seen" in out
    assert "PASS" in out
    assert "Smoke test passed." in out


async def test_run_fails_with_the_context_fix_when_the_prompt_was_cut(
    settings_factory: SettingsFactory,
    fixed_codes: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    llm = _ShortPromptLLM({Role.COACH: ["ready", "ready", "FIRST=NONE; LAST=LAST-2222"]})

    code = await run(llm, settings_factory(), [Role.COACH])

    out = capsys.readouterr().out
    assert code == 1
    assert "first-line code: MISSING" in out
    assert "OLLAMA_CONTEXT_LENGTH=16384" in out
    assert "truncates long prompts from the START" in out
    assert "Smoke test FAILED." in out


async def test_run_reports_a_failing_role_and_exits_nonzero(
    settings_factory: SettingsFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    llm = FakeLLM({Role.GATE: [ModelUnavailable("refused")]})

    code = await run(llm, settings_factory(), [Role.GATE])

    assert code == 1
    assert "FAILED MODEL_UNAVAILABLE" in capsys.readouterr().out


async def test_run_fails_when_thinking_text_leaks(
    settings_factory: SettingsFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    llm = FakeLLM({Role.GATE: ["ready <think", "ready"]})
    assert await run(llm, settings_factory(), [Role.GATE]) == 1
    assert "YES" in capsys.readouterr().out
