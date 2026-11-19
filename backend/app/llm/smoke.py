"""Smoke test against the real model endpoint.

    uv run python -m app.llm.smoke [--role gate|client|coach|all]

For each role, sends a tiny prompt twice (cold, then warm) and reports the model, latency,
tokens, a preview of the reply and whether any thinking text leaked into it. For the coach,
also sends a ~6,000-token prompt to check that the whole prompt reaches the model.
"""

import argparse
import asyncio
import logging
import secrets
import string
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from app.config import Settings, get_settings
from app.llm import (
    ChatMessage,
    LLMClient,
    LLMError,
    LLMResult,
    Role,
    endpoint_host,
    get_llm,
    resolve_model,
)
from app.logging_setup import configure_logging

# Diagnostic probes, not product prompts (those live in app/prompts).
TINY_PROMPT = [ChatMessage(role="user", content="Reply with exactly one word: ready")]
# Leaves room for models that reason before answering even when asked not to (gpt-oss).
TINY_MAX_TOKENS = 512
LONG_TARGET_TOKENS = 6000
LONG_MAX_TOKENS = 1024
SMOKE_PROMPT_VERSION = "smoke"

# Deliberately generous: gpt-oss packs this filler at ~4.9 characters per token and qwen at
# ~4, so the real count lands at or above the estimate, well clear of a 4,096-token cut.
_CHARS_PER_TOKEN = 5
_SIZE_FLOOR = 0.75  # a prompt that arrives smaller than this share of the estimate was cut
_THINK_MARKERS = ("<think", "</think", "<thinking", "</thinking")
_FILLER = "Line {n:04d}: the quarterly statement lists routine card payments, transfers and fees.\n"

CONTEXT_FIX = (
    "Ollama silently truncates long prompts from the START, so the system prompt is lost "
    "first.\n  Fix: set OLLAMA_CONTEXT_LENGTH=16384 for the Ollama server (Windows: "
    "`setx OLLAMA_CONTEXT_LENGTH 16384`),\n  then quit and restart Ollama."
)


@dataclass(frozen=True)
class LongPromptCheck:
    """Outcome of the long-prompt check."""

    expected_tokens: int
    prompt_tokens: int | None
    first_seen: bool
    last_seen: bool

    @property
    def size_ok(self) -> bool:
        return (
            self.prompt_tokens is not None
            and self.prompt_tokens >= _SIZE_FLOOR * self.expected_tokens
        )

    @property
    def passed(self) -> bool:
        return self.size_ok and self.first_seen and self.last_seen


def thinking_leaked(text: str) -> bool:
    """True if reasoning markup survived into the reply text."""
    lowered = text.lower()
    return any(marker in lowered for marker in _THINK_MARKERS)


def random_code() -> str:
    """A fresh code such as `QZKW-4821`; random so no cache or guess can supply it."""
    letters = "".join(secrets.choice(string.ascii_uppercase) for _ in range(4))
    return f"{letters}-{secrets.randbelow(10_000):04d}"


def build_long_prompt(
    first_code: str, last_code: str, target_tokens: int = LONG_TARGET_TOKENS
) -> tuple[list[ChatMessage], int]:
    """Return the long-prompt probe and its expected size in tokens.

    The first code opens the system message, which is where a cut from the start does its
    damage; the last code is the final line of the user message.
    """
    system = (
        f"FIRST CODE: {first_code}\n"
        "You are checking that you can read a whole document. Follow the final instruction."
    )
    lines: list[str] = []
    size = len(system)
    while size < target_tokens * _CHARS_PER_TOKEN:
        lines.append(_FILLER.format(n=len(lines) + 1))
        size += len(lines[-1])
    user = (
        "".join(lines)
        + "What are the FIRST CODE and the LAST CODE? Answer exactly as: "
        + "FIRST=<code>; LAST=<code>\n"
        + f"LAST CODE: {last_code}"
    )
    expected = (len(system) + len(user)) // _CHARS_PER_TOKEN
    messages = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=user),
    ]
    return messages, expected


async def run_long_prompt_check(llm: LLMClient) -> tuple[LongPromptCheck, LLMResult]:
    """Send the long prompt to the coach and check that both codes and all tokens arrived."""
    first, last = random_code(), random_code()
    messages, expected = build_long_prompt(first, last)
    result = await llm.chat(
        Role.COACH,
        messages,
        max_tokens=LONG_MAX_TOKENS,
        temperature=0,
        prompt_version=SMOKE_PROMPT_VERSION,
    )
    reply = result.text.upper()
    check = LongPromptCheck(
        expected_tokens=expected,
        prompt_tokens=result.prompt_tokens,
        first_seen=first in reply,
        last_seen=last in reply,
    )
    return check, result


async def run(llm: LLMClient, settings: Settings, roles: Sequence[Role]) -> int:
    """Run the smoke test and print a report. Returns the process exit code."""
    ok = True
    thinking = "disabled" if settings.LLM_DISABLE_THINKING else "allowed"
    _say(f"Model endpoint: {endpoint_host(settings.LLM_BASE_URL)} (thinking {thinking})\n")
    _say(f"{'role':<7} {'model':<22} {'run':<5} {'latency':>9} {'tokens in/out':>14}  leak  reply")
    for role in roles:
        model = resolve_model(role, None, settings=settings)
        for run_label in ("cold", "warm"):
            try:
                result = await llm.chat(
                    role,
                    TINY_PROMPT,
                    max_tokens=TINY_MAX_TOKENS,
                    temperature=0,
                    prompt_version=SMOKE_PROMPT_VERSION,
                )
            except LLMError as exc:
                ok = False
                _say(f"{role.value:<7} {model:<22} {run_label:<5} FAILED {exc.code}: {exc.detail}")
                break
            leaked = thinking_leaked(result.text)
            ok = ok and not leaked and bool(result.text)
            tokens = f"{result.prompt_tokens}/{result.completion_tokens}"
            _say(
                f"{role.value:<7} {result.model:<22} {run_label:<5} "
                f"{result.latency_ms / 1000:>7.2f} s {tokens:>14}  "
                f"{'YES' if leaked else 'no':<4}  {_preview(result.text)}"
            )
    if Role.COACH in roles:
        ok = await _report_long_prompt(llm, settings) and ok
    _say("\nSmoke test passed." if ok else "\nSmoke test FAILED.")
    return 0 if ok else 1


async def _report_long_prompt(llm: LLMClient, settings: Settings) -> bool:
    model = resolve_model(Role.COACH, None, settings=settings)
    _say(f"\nLong-prompt check (coach, {model}): about {LONG_TARGET_TOKENS:,} tokens")
    try:
        check, result = await run_long_prompt_check(llm)
    except LLMError as exc:
        _say(f"  FAILED {exc.code}: {exc.detail}")
        return False
    floor = round(_SIZE_FLOOR * check.expected_tokens)
    arrived = "unknown" if check.prompt_tokens is None else f"{check.prompt_tokens:,}"
    _say(
        f"  prompt_tokens: {arrived} "
        f"(expected about {check.expected_tokens:,}; at least {floor:,} needed)"
    )
    _say(
        f"  first-line code: {'seen' if check.first_seen else 'MISSING'} | "
        f"last-line code: {'seen' if check.last_seen else 'MISSING'} | "
        f"latency {result.latency_ms / 1000:.2f} s"
    )
    if check.passed:
        _say("  PASS: the model saw the whole prompt.")
        return True
    _say(f"  FAIL: the model did not see the whole prompt.\n  {CONTEXT_FIX}")
    if check.size_ok:
        _say(
            "  Note: prompt_tokens looks complete, so this may be a recall problem rather "
            "than the context window. Run the check again to confirm."
        )
    return False


def _preview(text: str, limit: int = 40) -> str:
    flat = " ".join(text.split())
    return repr(flat if len(flat) <= limit else flat[: limit - 1] + "…")


def _say(line: str) -> None:
    # Console output of a CLI, not logging.
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments, run the smoke test and return the exit code."""
    parser = argparse.ArgumentParser(
        prog="python -m app.llm.smoke",
        description="Send tiny prompts to each role (and a long one to the coach).",
    )
    parser.add_argument("--role", choices=["gate", "client", "coach", "all"], default="all")
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(logging.WARNING, secrets=[settings.LLM_API_KEY.get_secret_value()])
    roles = list(Role) if args.role == "all" else [Role(args.role)]
    return asyncio.run(run(get_llm(), settings, roles))


if __name__ == "__main__":
    sys.exit(main())
