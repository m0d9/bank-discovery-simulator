"""InterviewService: the one code path for interviews, used by the API, scripts/ and evals/."""

import unicodedata
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from app.config import Settings
from app.content import ContentRegistry, LocalizedText, UnknownProduct
from app.llm import LLMClient, Role, resolve_model
from app.prompts import PROMPT_VERSION
from app.simulation.client_agent import (
    LanguageRetry,
    client_history,
    client_reminder,
    client_system_prompt,
    generate_reply,
)
from app.simulation.disclosure import run_gate
from app.simulation.errors import InvalidInput, InvalidState, TurnLimitReached
from app.simulation.models import Language, Session, SessionModels, SessionStatus, Turn, WrapUp
from app.simulation.store import SessionStore
from app.telemetry.events import EventLogger

_KEPT_CONTROLS = frozenset("\n\t")


def clean_message(text: str) -> str:
    """The student's text without control characters (newlines and tabs stay), trimmed."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    kept = (ch for ch in text if ch in _KEPT_CONTROLS or unicodedata.category(ch) != "Cc")
    return "".join(kept).strip()


@dataclass(frozen=True)
class TurnResult:
    """One completed exchange, and what happened behind it (for `--debug` and the evals)."""

    session: Session
    student_turn: Turn
    client_turn: Turn
    eligible: tuple[str, ...]
    """Facts that could unlock this turn, decided before the gate ran."""
    unlocked_now: tuple[str, ...]
    unlocked_by_pitch: tuple[str, ...]
    products_mentioned: tuple[str, ...]
    gate_failed: bool
    gate_note: str
    gate_rejected: tuple[str, ...]
    """Facts the gate unlocked with a quote that isn't in that fact's `unlock_when`."""
    gate_quotes: Mapping[str, str]
    """The behaviour the gate quoted for each fact it unlocked itself."""
    role_break: bool
    regenerated: bool
    language_retry: LanguageRetry | None
    """Set when the client's reply was in the wrong language and was regenerated."""
    latency_ms: Mapping[str, int]
    """Milliseconds per role (`gate`, `client`), retries included."""


class InterviewService:
    """Create interviews, run each student message through the gate and the client, wrap up.

    Build one per request (the API) or once per process (scripts, evals): the sessions live in
    the `SessionStore`, so the service itself holds no state.
    """

    def __init__(
        self,
        *,
        store: SessionStore,
        llm: LLMClient,
        settings: Settings,
        events: EventLogger,
        content: ContentRegistry,
    ) -> None:
        self._store = store
        self._llm = llm
        self._settings = settings
        self._events = events
        self._content = content

    async def create_session(self, client_id: str, language: Language) -> Session:
        """Start an interview. Turn 0 is the client's opening line, from the content.

        Raises `UnknownClient`. Each role's model is fixed now, for the whole session.
        """
        client = self._content.get_client(client_id)
        now = self._store.now()
        models = SessionModels(
            gate=resolve_model(Role.GATE, settings=self._settings),
            client=resolve_model(Role.CLIENT, settings=self._settings),
            coach=resolve_model(Role.COACH, settings=self._settings),
        )
        opening = Turn(n=0, role="client", text=_in(client.card.opening_line, language), ts=now)
        session = Session(
            id=str(uuid.uuid4()),
            client_id=client.id,
            language=language,
            models=models,
            turns=[opening],
            created_at=now,
            last_active_at=now,
            client=client,
            bank=self._content.bank,
            products={product.id: product for product in self._content.list_products()},
        )
        self._store.create(session)
        await self._events.emit(
            "session_created",
            session_id=session.id,
            client_id=client.id,
            language=language,
            models=models.model_dump(),
        )
        return session

    def get_session(self, session_id: str) -> Session:
        """Return the session, or raise `SessionNotFound`. Reading it counts as activity."""
        session = self._store.get(session_id)
        self._store.touch(session_id)
        return session

    async def student_message(self, session_id: str, text: str) -> TurnResult:
        """Run one student message: guard it, ask the gate, then the client.

        The exchange is saved only once the client's reply is ready: if a model call fails,
        the session is left exactly as it was and the error propagates. A gate failure doesn't
        fail the turn; it just unlocks nothing.

        Raises `SessionNotFound`, `SessionBusy`, `InvalidState`, `TurnLimitReached`,
        `InvalidInput`, or the client role's `LLMError`.
        """
        async with self._store.locked(session_id) as session:
            self._store.touch(session_id)
            if session.status is not SessionStatus.INTERVIEWING:
                raise InvalidState("the interview has ended")
            limit = self._settings.MAX_STUDENT_TURNS
            if session.student_turns_used >= limit:
                raise TurnLimitReached(f"the interview allows {limit} student messages")
            message = clean_message(text)
            if not message:
                raise InvalidInput("the message is empty")
            if len(message) > self._settings.MAX_MESSAGE_CHARS:
                limit_chars = self._settings.MAX_MESSAGE_CHARS
                raise InvalidInput(f"the message is longer than {limit_chars} characters")

            n = session.turns[-1].n + 1
            products = list(session.products.values())
            gate = await run_gate(
                self._llm,
                model=session.models.gate,
                client=session.client,
                products=products,
                unlocked=session.unlocked.keys(),
                client_reply=session.turns[-1].text,
                student_message=message,
                max_unlocks=self._settings.MAX_UNLOCKS_PER_TURN,
            )
            student_turn = Turn(
                n=n,
                role="student",
                text=message,
                ts=self._store.now(),
                unlocked=list(gate.unlocked),
                unlocked_by_pitch=list(gate.by_pitch),
            )
            unlocked_after = {*session.unlocked, *gate.unlocked}
            # The client knows only the products the student has brought up: knowing the rest,
            # it hinted at the right one ("an Islamic option for working capital").
            mentioned = {*session.products_mentioned, *gate.products_mentioned}
            discussed = [product for product in products if product.id in mentioned]
            reply = await generate_reply(
                self._llm,
                model=session.models.client,
                system_prompt=client_system_prompt(
                    session.client, session.bank, discussed, unlocked=unlocked_after
                ),
                reminder=client_reminder(session.client, session.bank),
                history=client_history(
                    [*session.turns, student_turn], self._settings.CLIENT_HISTORY_TURNS
                ),
                language=session.language,
            )

            # Save the whole exchange at once: nothing above changed the session.
            client_turn = Turn(n=n + 1, role="client", text=reply.text, ts=self._store.now())
            session.turns.extend([student_turn, client_turn])
            session.unlocked.update(dict.fromkeys(gate.unlocked, n))
            for product_id in gate.products_mentioned:
                session.products_mentioned.setdefault(product_id, []).append(n)
            self._store.touch(session_id)

            result = TurnResult(
                session=session,
                student_turn=student_turn,
                client_turn=client_turn,
                eligible=gate.eligible,
                unlocked_now=gate.unlocked,
                unlocked_by_pitch=gate.by_pitch,
                products_mentioned=gate.products_mentioned,
                gate_failed=gate.failed,
                gate_note=gate.note,
                gate_rejected=gate.rejected,
                gate_quotes=gate.quotes,
                role_break=reply.role_break,
                regenerated=reply.regenerated,
                language_retry=reply.language_retry,
                latency_ms=MappingProxyType({"gate": gate.latency_ms, "client": reply.latency_ms}),
            )
            await self._emit_turn(result)
            return result

    async def wrap_up(self, session_id: str, wrapup: WrapUp) -> Session:
        """Record the student's summary and recommendations; the status becomes `wrapped_up`.

        Raises `SessionNotFound`, `SessionBusy`, `InvalidState` (the interview has already
        ended, or the student hasn't asked anything yet) or `UnknownProduct`.
        """
        async with self._store.locked(session_id) as session:
            self._store.touch(session_id)
            if session.status is not SessionStatus.INTERVIEWING:
                raise InvalidState("the interview has already been wrapped up")
            if session.student_turns_used == 0:
                raise InvalidState("send the client at least one message before wrapping up")
            for recommendation in wrapup.recommendations:
                if recommendation.product_id not in session.products:
                    raise UnknownProduct(recommendation.product_id)
            session.wrapup = wrapup
            session.status = SessionStatus.WRAPPED_UP
            await self._events.emit(
                "wrapped_up",
                session_id=session.id,
                client_id=session.client_id,
                student_turns=session.student_turns_used,
                recommended=[item.product_id for item in wrapup.recommendations],
                unlocked=list(session.unlocked),
            )
            return session

    async def delete_session(self, session_id: str) -> None:
        """Remove the session. Raises `SessionNotFound`, or `SessionBusy` mid-turn."""
        async with self._store.locked(session_id):
            self._store.delete(session_id)

    async def _emit_turn(self, result: TurnResult) -> None:
        session = result.session
        fields: dict[str, object] = {
            "session_id": session.id,
            "client_id": session.client_id,
            "student_turn_no": session.student_turns_used,
            "unlocked": list(result.unlocked_now),
            "products_mentioned": list(result.products_mentioned),
            "gate_failed": result.gate_failed,
            "gate_rejected": list(result.gate_rejected),
            "role_break": result.role_break,
            "regenerated": result.regenerated,
            "latency_ms": dict(result.latency_ms),
            "models": {"gate": session.models.gate, "client": session.models.client},
            "prompt_versions": {
                name: PROMPT_VERSION[name]
                for name in ("gate", "client_system", "client_reminder", "client_language")
            },
        }
        if self._settings.LOG_TRANSCRIPTS:
            fields["student_text"] = result.student_turn.text
            fields["client_text"] = result.client_turn.text
            fields["gate_note"] = result.gate_note
        await self._events.emit("turn", **fields)
        retry = result.language_retry
        if retry is not None:
            mismatch: dict[str, object] = {
                "session_id": session.id,
                "client_id": session.client_id,
                "student_turn_no": session.student_turns_used,
                "reason": retry.reason,
                "retried": retry.retried,
                "fixed": retry.fixed,
            }
            if self._settings.LOG_TRANSCRIPTS:
                mismatch["first_text"] = retry.first_text
            await self._events.emit("language_mismatch", **mismatch)


def _in(text: LocalizedText, language: Language) -> str:
    """The text in `language`, or the English when there's no Arabic."""
    return text.ar if language == "ar" and text.ar else text.en
