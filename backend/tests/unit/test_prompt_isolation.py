"""Prompt isolation, the interview engine's most important tests (docs/architecture.md).

Every message sent to a model is captured, and one checker walks through all of them against
the timeline of unlocks:
- A hidden fact's content never reaches the gate, and reaches the client only from the turn
  that unlocked it.
- A signal reaches the client only while its fact is eligible and still locked, and never
  reaches the gate.
- The gate never sees the transcript: only the previous client reply and the new message.

The checks run through `InterviewService`, the same code path as the API.
"""

from collections.abc import Sequence
from typing import Any

import pytest

from app.config import Settings
from app.content import ContentRegistry, load_registry
from app.llm import Role
from app.llm.fake import FakeCall, FakeLLM, Scripted
from app.simulation import InterviewService, Session
from app.simulation.disclosure import eligible_facts
from tests.content_factory import ALPHA, CLIENT
from tests.interview_factory import (
    REPO_CONTENT,
    client_data_with,
    gate_reply,
    hidden_fact,
    make_service,
    quote,
    registry,
)

FACTS = (
    hidden_fact("cash-gap", signal="SIGNAL-CASH-GAP"),
    hidden_fact("expansion", importance="important", requires=["cash-gap"], signal="SIGNAL-EXP"),
    hidden_fact("pitch-reaction", importance="minor", pitch=[ALPHA], signal="SIGNAL-PITCH"),
)

# One step per student message: what the gate answers, and what the client says (twice when
# the first reply breaks character and is regenerated).
Step = tuple[dict[str, Any], Sequence[Scripted]]


def question(k: int) -> str:
    return f"Q{k}: the student's question number {k}?"


def reply(k: int) -> str:
    return f"R{k}: the client's reply number {k}."


async def interview(
    service: InterviewService, fake: FakeLLM, client_id: str, steps: Sequence[Step]
) -> Session:
    session = await service.create_session(client_id, "en")
    for k, (gate, client_texts) in enumerate(steps, start=1):
        fake.script(Role.GATE, gate)
        fake.script(Role.CLIENT, *client_texts)
        await service.student_message(session.id, question(k))
    return session


def calls_by_turn(calls: Sequence[FakeCall]) -> list[tuple[int, FakeCall]]:
    """Pair each call with its 1-based student turn: every turn starts with one gate call."""
    paired, turn = [], 0
    for call in calls:
        turn += call.role is Role.GATE
        paired.append((turn, call))
    return paired


def text_of(call: FakeCall) -> str:
    return "\n".join(message.content for message in call.messages)


def isolation_problems(calls: Sequence[FakeCall], session: Session) -> list[str]:
    """Every way the captured calls break prompt isolation (empty when they don't)."""
    problems = []
    for turn, call in calls_by_turn(calls):
        n = 2 * turn - 1  # the student turn's `n`
        text = text_of(call)
        # The gate runs before this turn's unlocks; the client replies after them.
        unlocked = {
            fact_id
            for fact_id, at in session.unlocked.items()
            if at < n or (call.role is Role.CLIENT and at == n)
        }
        eligible = {fact.id for fact in eligible_facts(session.client, unlocked)}
        for fact in session.client.hidden_facts:
            where = f"turn {turn}, {call.role.value}"
            if fact.content in text and (call.role is Role.GATE or fact.id not in unlocked):
                problems.append(f"{where}: content of {fact.id} (unlocked: {sorted(unlocked)})")
            signal_seen = bool(fact.signal) and fact.signal in text
            if signal_seen and (call.role is Role.GATE or fact.id not in eligible):
                problems.append(f"{where}: signal of {fact.id} (eligible: {sorted(eligible)})")
    return problems


def transcript_problems(calls: Sequence[FakeCall], session: Session) -> list[str]:
    """Gate calls that include anything older than the previous client reply."""
    problems = []
    opening = session.turns[0].text
    gate_calls = [call for call in calls if call.role is Role.GATE]
    assert len(gate_calls) == session.student_turns_used
    for k, call in enumerate(gate_calls, start=1):
        text = text_of(call)
        older = [question(j) for j in range(1, k)] + [reply(j) for j in range(1, k - 1)]
        if k > 1:
            older.append(opening)
        problems += [f"gate call {k} saw {item!r}" for item in older if item in text]
        previous = reply(k - 1) if k > 1 else opening
        if previous not in text or question(k) not in text:
            problems.append(f"gate call {k} lacks the previous reply or the new message")
    return problems


async def test_facts_and_signals_reach_only_the_client_and_only_when_allowed(
    settings: Settings,
) -> None:
    fake = FakeLLM()
    service = make_service(settings, fake, registry(client_data_with(*FACTS)))
    steps: list[Step] = [
        (gate_reply(), [reply(1)]),
        (gate_reply("cash-gap"), ["As an AI, I can't say.", reply(2)]),  # regenerated
        (gate_reply("expansion", products=[ALPHA]), [reply(3)]),  # + pitch-reaction
        (gate_reply(), [reply(4)]),
    ]

    session = await interview(service, fake, CLIENT, steps)

    assert session.unlocked == {"cash-gap": 3, "expansion": 5, "pitch-reaction": 5}
    assert isolation_problems(fake.calls, session) == []
    assert transcript_problems(fake.calls, session) == []

    # Positive controls, so the checker can't pass by seeing nothing at all.
    by_turn: dict[int, list[str]] = {}
    for turn, call in calls_by_turn(fake.calls):
        if call.role is Role.CLIENT:
            by_turn.setdefault(turn, []).append(text_of(call))
    secret = {fact["id"]: fact["content"] for fact in FACTS}
    assert all("SIGNAL-CASH-GAP" in t and "SIGNAL-PITCH" in t for t in by_turn[1])
    assert not any("SIGNAL-EXP" in t for t in by_turn[1])
    assert len(by_turn[2]) == 2  # the reply and its regeneration
    assert all(secret["cash-gap"] in t and "SIGNAL-EXP" in t for t in by_turn[2])
    assert all(secret["expansion"] in t and secret["pitch-reaction"] in t for t in by_turn[3])
    assert not any("SIGNAL-" in t for t in by_turn[3] + by_turn[4])


# Every client file in the repository, so a new client is covered without editing this test.
REAL_CLIENT_IDS = sorted(path.stem for path in (REPO_CONTENT / "clients").glob("[!_]*.yaml"))


@pytest.mark.parametrize("client_id", REAL_CLIENT_IDS)
async def test_the_real_clients_keep_their_facts_out_of_every_prompt_until_unlocked(
    settings: Settings, client_id: str
) -> None:
    content: ContentRegistry = load_registry(settings.CONTENT_DIR)
    client = content.get_client(client_id)
    fake = FakeLLM()
    service = make_service(settings, fake, content)
    # One generic turn, then one fact per turn in dependency order.
    order: list[str] = []
    while len(order) < len(client.hidden_facts):
        order.append(eligible_facts(client, set(order))[0].id)
    steps: list[Step] = [(gate_reply(), [reply(1)])]
    steps += [
        (gate_reply(quote(client, fact_id)), [reply(k)]) for k, fact_id in enumerate(order, start=2)
    ]

    session = await interview(service, fake, client_id, steps)

    assert list(session.unlocked) == order
    assert isolation_problems(fake.calls, session) == []
    assert transcript_problems(fake.calls, session) == []
