"""Interview a client in the terminal, through the same InterviewService as the API.

    uv run --project backend python scripts/chat.py --client noura-al-kuwari \
        [--lang en] [--debug] [--script path.txt]
    make chat CLIENT=noura-al-kuwari [DEBUG=1] [SCRIPT=scripts/chat-scripts/noura-al-kuwari.txt]

`--script` reads one student message per line and runs without interaction. Blank lines and
lines starting with `#` are skipped. `--debug` prints, after every turn, the eligible facts, the
facts that turn unlocked, every fact unlocked so far, the products mentioned and the latency per
role. Without `--script`, type each message; an empty line or Ctrl-D ends the interview.
"""

import argparse
import asyncio
import sys
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import TextIO

from pydantic import ValidationError

from app.config import Settings, get_settings
from app.content import ContentValidationError, UnknownClient, load_registry
from app.llm import LLMClient, LLMError, get_llm
from app.logging_setup import configure_logging
from app.simulation import (
    InterviewError,
    InterviewService,
    Language,
    Session,
    SessionStore,
    TurnLimitReached,
    TurnResult,
)
from app.telemetry.events import event_logger_for


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scripts/chat.py",
        description="Interview an AI bank client in the terminal.",
    )
    parser.add_argument("--client", required=True, help="client id, e.g. noura-al-kuwari")
    parser.add_argument("--lang", choices=["en", "ar"], default="en", help="session language")
    parser.add_argument("--debug", action="store_true", help="show the gate's work after each turn")
    parser.add_argument("--script", type=Path, help="file with one student message per line")
    return parser.parse_args(argv)


def script_lines(path: Path) -> Iterator[str]:
    """The student messages in a script file."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            yield line.strip()


def typed_lines() -> Iterator[str]:
    """Student messages typed at the prompt, until an empty line or end of input."""
    while True:
        try:
            line = input("You: ")
        except (EOFError, KeyboardInterrupt):
            return
        if not line.strip():
            return
        yield line


async def run(
    args: argparse.Namespace,
    *,
    settings: Settings,
    llm: LLMClient,
    lines: Iterable[str],
    out: TextIO,
    echo: bool,
) -> int:
    """Run one interview and return the exit code."""
    content = load_registry(settings.CONTENT_DIR)
    service = InterviewService(
        store=SessionStore.from_settings(settings),
        llm=llm,
        settings=settings,
        events=event_logger_for(settings.DATA_DIR),
        content=content,
    )
    language: Language = args.lang
    try:
        session = await service.create_session(args.client, language)
    except UnknownClient:
        known = ", ".join(client.id for client in content.list_clients())
        _say(out, f"No client has the id {args.client!r}. Clients: {known}")
        return 2
    card = session.client.card.name
    name = card.ar if language == "ar" and card.ar else card.en
    _say(out, f"{name}: {session.turns[0].text}")
    if args.debug:
        models = session.models
        _say(out, f"  [debug] models: gate {models.gate} · client {models.client}")
    for message in lines:
        if echo:
            _say(out, f"You: {message}")
        try:
            result = await service.student_message(session.id, message)
        except TurnLimitReached as exc:
            _say(out, f"  [{exc.code}] {exc.detail}")
            break
        except (InterviewError, LLMError) as exc:
            _say(out, f"  [{exc.code}] {exc.detail}")
            continue
        _say(out, f"{name}: {result.client_turn.text}")
        if args.debug:
            for line in debug_lines(result, session):
                _say(out, f"  [debug] {line}")
    return 0


def debug_lines(result: TurnResult, session: Session) -> list[str]:
    """What the gate saw and decided this turn, with the latency per role (ids only)."""
    pitched = set(result.unlocked_by_pitch)
    unlocked_now = [
        f"{fact_id} (product pitch)" if fact_id in pitched else fact_id
        for fact_id in result.unlocked_now
    ]
    so_far = [f"{fact_id} (t{n})" for fact_id, n in session.unlocked.items()]
    latency = result.latency_ms
    flags = (
        f"gate failed: {_yes(result.gate_failed)} · regenerated: {_yes(result.regenerated)}"
        f" · fallback line: {_yes(result.role_break)}"
    )
    return [
        f"eligible: {_ids(result.eligible)}",
        f"unlocked this turn: {_ids(unlocked_now)}",
        f"unlocked so far: {_ids(so_far)}",
        f"products mentioned: {_ids(result.products_mentioned)}",
        f"latency: gate {latency['gate']} ms · client {latency['client']} ms",
        flags,
        f"gate note: {result.gate_note or '-'}",
    ]


def main(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
    llm: LLMClient | None = None,
    out: TextIO = sys.stdout,
) -> int:
    """Parse the arguments, run the interview and return the exit code."""
    args = parse_args(argv)
    if settings is None:
        try:
            settings = get_settings()
        except ValidationError as exc:
            # Name the settings only: their values may include the API key.
            names = ", ".join(sorted({str(error["loc"][0]) for error in exc.errors()}))
            hint = f"Settings are missing or invalid ({names}). Copy .env.example to .env."
            _say(sys.stderr, hint)
            return 2
    # The same JSON logs as the app, on stderr; the transcript goes to `out`.
    configure_logging(secrets=[settings.LLM_API_KEY.get_secret_value()])
    if args.script is not None:
        lines: Iterable[str] = script_lines(args.script)
    else:
        lines = typed_lines()
    try:
        return asyncio.run(
            run(
                args,
                settings=settings,
                llm=llm or get_llm(),
                lines=lines,
                out=out,
                echo=args.script is not None,
            )
        )
    except ContentValidationError as exc:
        for message in exc.messages:
            _say(sys.stderr, message)
        return 1


def _ids(items: Iterable[str]) -> str:
    return ", ".join(items) or "-"


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"


def _say(stream: TextIO, line: str) -> None:
    # Console output of a CLI, not logging.
    stream.write(line + "\n")
    stream.flush()


if __name__ == "__main__":
    sys.exit(main())
