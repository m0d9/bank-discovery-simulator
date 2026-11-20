import asyncio
import json
from collections.abc import Sequence
from typing import Any

import pytest
from pydantic import BaseModel

from app.config import Settings
from app.content import UnknownClient, UnknownProduct
from app.llm import ChatMessage, LLMResult, ModelTimeout, Role
from app.llm.fake import FakeLLM
from app.simulation import (
    InterviewService,
    InvalidInput,
    InvalidState,
    Recommendation,
    SessionBusy,
    SessionNotFound,
    SessionStatus,
    SessionStore,
    TurnLimitReached,
    WrapUp,
)
from app.simulation.service import clean_message
from tests.conftest import SettingsFactory
from tests.content_factory import ALPHA, BETA, CLIENT
from tests.interview_factory import (
    OPENING,
    client_data_with,
    gate_reply,
    hidden_fact,
    make_service,
    quote,
    registry,
)

# The factory's default client: cash-gap is earned by "asks how customers pay".
CASH_GAP = quote(registry().get_client(CLIENT), "cash-gap")
WRAPUP = WrapUp(
    needs_summary="The client needs to bridge late customer payments.",
    recommendations=[Recommendation(product_id=ALPHA, reason="It bridges the gap.")],
)


def read_events(settings: Settings) -> list[dict[str, Any]]:
    path = settings.DATA_DIR / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def say(
    service: InterviewService,
    fake: FakeLLM,
    session_id: str,
    text: str = "How do your customers pay you?",
    *,
    gate: dict[str, Any] | None = None,
    reply: str = "They pay late, sometimes.",
) -> Any:
    fake.script(Role.GATE, gate or gate_reply())
    fake.script(Role.CLIENT, reply)
    return await service.student_message(session_id, text)


@pytest.fixture
def fake() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def service(settings: Settings, fake: FakeLLM) -> InterviewService:
    return make_service(settings, fake)


async def test_a_new_session_opens_with_the_clients_line_and_fixed_models(
    settings_factory: SettingsFactory, fake: FakeLLM
) -> None:
    settings = settings_factory(LLM_MODEL_GATE="small:4b", LLM_MODEL_COACH="big:20b")
    service = make_service(settings, fake)

    session = await service.create_session(CLIENT, "en")

    assert [(t.n, t.role, t.text) for t in session.turns] == [(0, "client", OPENING)]
    assert session.models.model_dump() == {
        "gate": "small:4b",
        "client": "test-model",
        "coach": "big:20b",
    }
    assert session.status is SessionStatus.INTERVIEWING
    assert service.get_session(session.id) is session
    assert fake.calls == []  # the opening line needs no model
    [event] = read_events(settings)
    assert event["event"] == "session_created"
    assert {k: event[k] for k in ("session_id", "client_id", "language")} == {
        "session_id": session.id,
        "client_id": CLIENT,
        "language": "en",
    }


async def test_an_arabic_session_opens_in_arabic_when_the_content_has_it(
    settings: Settings, fake: FakeLLM
) -> None:
    data = client_data_with(hidden_fact("cash-gap"), hidden_fact("expansion"))
    data["card"]["opening_line"] = {"en": "Hello.", "ar": "مرحبًا."}
    service = make_service(settings, fake, registry(data))

    assert (await service.create_session(CLIENT, "ar")).turns[0].text == "مرحبًا."
    assert (await service.create_session(CLIENT, "en")).turns[0].text == "Hello."


async def test_an_unknown_client_cannot_start_a_session(service: InterviewService) -> None:
    with pytest.raises(UnknownClient):
        await service.create_session("nobody", "en")


async def test_a_turn_records_the_exchange_unlocks_and_product_mentions(
    service: InterviewService, fake: FakeLLM
) -> None:
    session = await service.create_session(CLIENT, "en")

    first = await say(service, fake, session.id, gate=gate_reply(CASH_GAP, products=[BETA]))
    second = await say(service, fake, session.id, "And then?", gate=gate_reply(products=[BETA]))

    assert [(t.n, t.role) for t in session.turns] == [
        (0, "client"),
        (1, "student"),
        (2, "client"),
        (3, "student"),
        (4, "client"),
    ]
    assert first.student_turn.unlocked == ["cash-gap"] and second.student_turn.unlocked == []
    assert session.unlocked == {"cash-gap": 1}
    assert session.products_mentioned == {BETA: [1, 3]}
    assert first.eligible == ("cash-gap",) and second.eligible == ("expansion",)
    assert session.student_turns_used == 2
    gate_input = json.loads(fake.calls_for(Role.GATE)[1].messages[1].content)
    assert gate_input["client_reply"] == "They pay late, sometimes."  # the previous reply
    assert gate_input["student_message"] == "And then?"


async def test_a_turn_records_which_unlocks_came_from_a_product_pitch(
    settings: Settings, fake: FakeLLM
) -> None:
    client = client_data_with(
        hidden_fact("asked-fact"), hidden_fact("pitch-reaction", importance="minor", pitch=[ALPHA])
    )
    service = make_service(settings, fake, registry(client))
    session = await service.create_session(CLIENT, "en")

    result = await say(service, fake, session.id, gate=gate_reply("asked-fact", products=[ALPHA]))

    assert result.student_turn.unlocked == ["asked-fact", "pitch-reaction"]
    assert result.student_turn.unlocked_by_pitch == ["pitch-reaction"]
    assert result.client_turn.unlocked_by_pitch == []


async def test_the_client_sees_only_the_last_history_turns(
    settings_factory: SettingsFactory, fake: FakeLLM
) -> None:
    service = make_service(settings_factory(CLIENT_HISTORY_TURNS=3), fake)
    session = await service.create_session(CLIENT, "en")
    await say(service, fake, session.id, "First question?", reply="First reply.")

    await say(service, fake, session.id, "Second question?")

    messages = fake.calls_for(Role.CLIENT)[-1].messages
    assert [(m.role, m.content) for m in messages[1:]] == [
        ("user", "First question?"),
        ("assistant", "First reply."),
        ("user", "Second question?"),
    ]


async def test_the_client_knows_only_the_products_the_student_has_mentioned(
    service: InterviewService, fake: FakeLLM
) -> None:
    session = await service.create_session(CLIENT, "en")

    await say(service, fake, session.id)
    await say(
        service, fake, session.id, "Would our Alpha Loan help?", gate=gate_reply(products=[ALPHA])
    )
    await say(service, fake, session.id, "What else would you need?")

    first, pitched, later = (call.messages[0].content for call in fake.calls_for(Role.CLIENT))
    for loan in ("Alpha Loan", "Beta Deposit"):
        assert loan not in first
    assert "- Alpha Loan: A business loan that charges interest." in pitched
    assert "Alpha Loan" in later and "Beta Deposit" not in pitched + later


def test_control_characters_are_removed_but_newlines_and_tabs_stay() -> None:
    assert clean_message("  Hi\x00 there\x07\r\nnext\tline\x1b  ") == "Hi there\nnext\tline"


@pytest.mark.parametrize("text", ["", "   ", "\x00\x07", "\n\t\n"])
async def test_an_empty_message_is_invalid_input(
    service: InterviewService, fake: FakeLLM, text: str
) -> None:
    session = await service.create_session(CLIENT, "en")
    with pytest.raises(InvalidInput, match="empty"):
        await service.student_message(session.id, text)
    assert fake.calls == []


async def test_the_message_length_limit_counts_the_cleaned_text(
    settings_factory: SettingsFactory, fake: FakeLLM
) -> None:
    service = make_service(settings_factory(MAX_MESSAGE_CHARS=10), fake)
    session = await service.create_session(CLIENT, "en")

    await say(service, fake, session.id, "  ten chars \x00 ")  # 10 characters once cleaned
    with pytest.raises(InvalidInput, match="longer than 10 characters"):
        await service.student_message(session.id, "eleven char")


async def test_the_turn_limit_is_enforced(settings_factory: SettingsFactory, fake: FakeLLM) -> None:
    service = make_service(settings_factory(MAX_STUDENT_TURNS=2), fake)
    session = await service.create_session(CLIENT, "en")
    await say(service, fake, session.id)
    await say(service, fake, session.id)

    with pytest.raises(TurnLimitReached):
        await service.student_message(session.id, "One more?")
    assert session.student_turns_used == 2


async def test_a_failed_client_reply_leaves_the_session_unchanged(
    service: InterviewService, fake: FakeLLM
) -> None:
    session = await service.create_session(CLIENT, "en")
    await say(service, fake, session.id)
    before = session.model_dump()
    fake.script(Role.GATE, gate_reply(CASH_GAP, products=[ALPHA]))
    fake.script(Role.CLIENT, ModelTimeout("slow"))

    with pytest.raises(ModelTimeout):
        await service.student_message(session.id, "Resent later")

    assert session.model_dump(exclude={"last_active_at"}) == {
        k: v for k, v in before.items() if k != "last_active_at"
    }
    retried = await say(service, fake, session.id, "Resent later", gate=gate_reply(CASH_GAP))
    assert retried.student_turn.n == 3  # no gap or duplicate left by the failure


async def test_a_failed_gate_unlocks_nothing_but_the_turn_goes_on(
    service: InterviewService, fake: FakeLLM
) -> None:
    session = await service.create_session(CLIENT, "en")
    fake.script(Role.GATE, ModelTimeout("slow"))
    fake.script(Role.CLIENT, "They pay late.")

    result = await service.student_message(session.id, "How do your customers pay you?")

    assert result.gate_failed and result.unlocked_now == ()
    assert result.client_turn.text == "They pay late."
    assert session.unlocked == {}


async def test_the_turn_event_has_ids_and_no_text_by_default(
    settings: Settings, service: InterviewService, fake: FakeLLM
) -> None:
    session = await service.create_session(CLIENT, "en")
    await say(service, fake, session.id, gate=gate_reply(CASH_GAP, note="asks how they pay"))

    turn = read_events(settings)[-1]
    assert turn["event"] == "turn"
    assert {k: turn[k] for k in ("session_id", "client_id", "student_turn_no")} == {
        "session_id": session.id,
        "client_id": CLIENT,
        "student_turn_no": 1,
    }
    assert (turn["unlocked"], turn["gate_failed"], turn["role_break"]) == (
        ["cash-gap"],
        False,
        False,
    )
    assert turn["gate_rejected"] == []
    assert set(turn["latency_ms"]) == {"gate", "client"}
    assert set(turn["models"]) == {"gate", "client"}
    assert set(turn["prompt_versions"]) == {
        "gate",
        "client_system",
        "client_reminder",
        "client_language",
    }
    line = json.dumps(turn)
    for text in ("How do your customers pay you?", "They pay late", "asks how they pay"):
        assert text not in line


async def test_a_misquoted_unlock_stays_locked_and_is_recorded_in_the_event(
    settings: Settings, service: InterviewService, fake: FakeLLM
) -> None:
    session = await service.create_session(CLIENT, "en")

    result = await say(service, fake, session.id, gate=gate_reply(("cash-gap", "asks about plans")))

    assert result.unlocked_now == () and result.gate_rejected == ("cash-gap",)
    assert session.unlocked == {}
    assert read_events(settings)[-1]["gate_rejected"] == ["cash-gap"]


async def test_the_turn_event_includes_the_texts_only_with_log_transcripts(
    settings_factory: SettingsFactory, fake: FakeLLM
) -> None:
    settings = settings_factory(LOG_TRANSCRIPTS=True)
    service = make_service(settings, fake)
    session = await service.create_session(CLIENT, "en")
    await say(service, fake, session.id, gate=gate_reply(note="asks how they pay"))

    turn = read_events(settings)[-1]
    assert turn["student_text"] == "How do your customers pay you?"
    assert turn["client_text"] == "They pay late, sometimes."
    assert turn["gate_note"] == "asks how they pay"


async def test_wrap_up_records_the_answer_and_ends_the_interview(
    settings: Settings, service: InterviewService, fake: FakeLLM
) -> None:
    session = await service.create_session(CLIENT, "en")
    await say(service, fake, session.id, gate=gate_reply(CASH_GAP))

    wrapped = await service.wrap_up(session.id, WRAPUP)

    assert wrapped.status is SessionStatus.WRAPPED_UP and wrapped.wrapup == WRAPUP
    event = read_events(settings)[-1]
    assert event["event"] == "wrapped_up"
    assert (event["recommended"], event["unlocked"], event["student_turns"]) == (
        [ALPHA],
        ["cash-gap"],
        1,
    )
    assert WRAPUP.needs_summary not in json.dumps(event)
    with pytest.raises(InvalidState, match="already been wrapped up"):
        await service.wrap_up(session.id, WRAPUP)
    with pytest.raises(InvalidState, match="ended"):
        await service.student_message(session.id, "One more question?")


async def test_wrap_up_needs_a_student_turn_and_known_products(
    service: InterviewService, fake: FakeLLM
) -> None:
    session = await service.create_session(CLIENT, "en")
    with pytest.raises(InvalidState, match="at least one message"):
        await service.wrap_up(session.id, WRAPUP)

    await say(service, fake, session.id)
    unknown = WRAPUP.model_copy(
        update={"recommendations": [Recommendation(product_id="nope", reason="Because.")]}
    )
    with pytest.raises(UnknownProduct):
        await service.wrap_up(session.id, unknown)
    assert session.status is SessionStatus.INTERVIEWING


async def test_a_deleted_session_is_gone(service: InterviewService) -> None:
    session = await service.create_session(CLIENT, "en")
    await service.delete_session(session.id)

    with pytest.raises(SessionNotFound):
        service.get_session(session.id)
    with pytest.raises(SessionNotFound):
        await service.delete_session(session.id)


class _SlowGate(FakeLLM):
    """A FakeLLM whose gate waits until released, so a turn stays in progress."""

    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def chat_json[T: BaseModel](
        self,
        role: Role,
        messages: Sequence[ChatMessage],
        schema: type[T],
        *,
        model: str | None = None,
        max_tokens: int,
        temperature: float = 0,
        prompt_version: str | None = None,
    ) -> tuple[T, LLMResult]:
        self.started.set()
        await self.release.wait()
        return await super().chat_json(
            role,
            messages,
            schema,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            prompt_version=prompt_version,
        )


async def test_a_session_mid_turn_is_busy_for_every_other_change(settings: Settings) -> None:
    slow = _SlowGate()
    service = make_service(settings, slow)
    session = await service.create_session(CLIENT, "en")
    slow.script(Role.GATE, gate_reply())
    slow.script(Role.CLIENT, "They pay late.")

    turn = asyncio.create_task(service.student_message(session.id, "How do they pay?"))
    await slow.started.wait()
    with pytest.raises(SessionBusy):
        await service.student_message(session.id, "Are you there?")
    with pytest.raises(SessionBusy):
        await service.wrap_up(session.id, WRAPUP)
    with pytest.raises(SessionBusy):
        await service.delete_session(session.id)
    assert service.get_session(session.id).student_turns_used == 0  # reading is fine

    slow.release.set()
    assert (await turn).client_turn.text == "They pay late."


async def test_a_running_session_keeps_the_content_it_started_with(
    settings: Settings, fake: FakeLLM
) -> None:
    store = SessionStore.from_settings(settings)
    service = make_service(settings, fake, store=store)
    session = await service.create_session(CLIENT, "en")
    edited = client_data_with(hidden_fact("cash-gap"), hidden_fact("expansion"))
    edited["open_facts"] = ["EDITED-OPEN-FACT"]
    # The content reloads with an edited client: a new service sees it, the session doesn't.
    reloaded = make_service(settings, fake, registry(edited), store=store)

    await say(reloaded, fake, session.id)

    system = fake.calls_for(Role.CLIENT)[-1].messages[0].content
    assert "EDITED-OPEN-FACT" not in system and "Runs a company in Doha." in system


async def test_a_reply_in_the_wrong_language_is_regenerated_and_logged_without_text(
    settings: Settings, service: InterviewService, fake: FakeLLM
) -> None:
    session = await service.create_session(CLIENT, "en")
    fake.script(Role.GATE, gate_reply())
    fake.script(Role.CLIENT, "يدفعون متأخرين أحيانًا.", "They pay late, sometimes.")

    result = await service.student_message(session.id, "How do your customers pay you?")

    assert result.client_turn.text == "They pay late, sometimes."
    event = read_events(settings)[-1]
    assert event["event"] == "language_mismatch"
    fields = ("session_id", "client_id", "student_turn_no", "reason", "retried", "fixed")
    assert {key: event[key] for key in fields} == {
        "session_id": session.id,
        "client_id": CLIENT,
        "student_turn_no": 1,
        "reason": "script",
        "retried": True,
        "fixed": True,
    }
    assert "first_text" not in event
    assert "يدفعون" not in json.dumps(event, ensure_ascii=False)


async def test_the_language_event_has_the_first_reply_only_with_log_transcripts(
    settings_factory: SettingsFactory, fake: FakeLLM
) -> None:
    settings = settings_factory(LOG_TRANSCRIPTS=True)
    service = make_service(settings, fake)
    session = await service.create_session(CLIENT, "en")
    fake.script(Role.GATE, gate_reply())
    fake.script(Role.CLIENT, "يدفعون متأخرين أحيانًا.", "يدفعون متأخرين.")

    await service.student_message(session.id, "How do your customers pay you?")

    event = read_events(settings)[-1]
    assert (event["event"], event["retried"], event["fixed"]) == ("language_mismatch", True, False)
    assert event["first_text"] == "يدفعون متأخرين أحيانًا."


async def test_a_reply_in_the_right_language_logs_no_language_event(
    settings: Settings, service: InterviewService, fake: FakeLLM
) -> None:
    session = await service.create_session(CLIENT, "en")

    result = await say(service, fake, session.id)

    assert result.language_retry is None
    assert [event["event"] for event in read_events(settings)] == ["session_created", "turn"]
