"""FakeLLM: a scripted `LLMClient` for tests. It never touches the network."""

import json
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from app.llm.errors import InvalidOutput, LLMError
from app.llm.json_output import parse_reply, strip_reasoning
from app.llm.roles import Role
from app.llm.types import ChatMessage, JsonMode, LLMResult

# One scripted response: reply text, a model or mapping (served as JSON), or an error to raise.
Scripted = str | BaseModel | Mapping[str, object] | LLMError

FAKE_MODEL = "fake-model"


@dataclass(frozen=True)
class FakeCall:
    """One call FakeLLM received."""

    method: Literal["chat", "chat_json"]
    role: Role
    model: str
    messages: tuple[ChatMessage, ...]
    max_tokens: int
    temperature: float
    prompt_version: str | None
    schema: type[BaseModel] | None = None


class FakeLLM:
    """Scripted `LLMClient`: a queue of responses or errors per role, and a record of calls.

    `chat_json` parses and validates scripted text the same way the real client does, so
    scripting malformed JSON raises InvalidOutput.
    """

    def __init__(
        self,
        script: Mapping[Role, Iterable[Scripted]] | None = None,
        *,
        models: Iterable[str] = (),
        list_models_error: LLMError | None = None,
        default_model: str = FAKE_MODEL,
    ) -> None:
        self._queues: dict[Role, deque[Scripted]] = {role: deque() for role in Role}
        for role, items in (script or {}).items():
            self._queues[role].extend(items)
        self.calls: list[FakeCall] = []
        self.models = list(models)
        self.list_models_error = list_models_error
        self.list_models_calls = 0
        self.default_model = default_model

    def script(self, role: Role, *items: Scripted) -> None:
        """Queue more responses for `role`."""
        self._queues[role].extend(items)

    def calls_for(self, role: Role) -> list[FakeCall]:
        """The recorded calls made by `role`, in order."""
        return [call for call in self.calls if call.role is role]

    async def chat(
        self,
        role: Role,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        max_tokens: int,
        temperature: float,
        prompt_version: str | None = None,
    ) -> LLMResult:
        """Return the next scripted reply for `role` as text."""
        name = model or self.default_model
        self.calls.append(
            FakeCall("chat", role, name, tuple(messages), max_tokens, temperature, prompt_version)
        )
        text = strip_reasoning(_as_text(self._next(role)))
        return _result(role, name, messages, text, "none")

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
        """Return the next scripted reply for `role`, validated as `schema`."""
        name = model or self.default_model
        self.calls.append(
            FakeCall(
                "chat_json",
                role,
                name,
                tuple(messages),
                max_tokens,
                temperature,
                prompt_version,
                schema,
            )
        )
        text = strip_reasoning(_as_text(self._next(role)))
        try:
            value = parse_reply(text, schema)
        except ValueError as exc:
            raise InvalidOutput(f"unusable JSON: {exc}", raw_text=text) from None
        return value, _result(role, name, messages, text, "schema")

    async def list_models(self) -> list[str]:
        """Return the configured model ids, or raise the configured error."""
        self.list_models_calls += 1
        if self.list_models_error is not None:
            raise self.list_models_error
        return list(self.models)

    def _next(self, role: Role) -> str | BaseModel | Mapping[str, object]:
        queue = self._queues[role]
        if not queue:
            raise AssertionError(f"FakeLLM: no scripted response left for role {role.value!r}")
        item = queue.popleft()
        if isinstance(item, LLMError):
            raise item
        return item


def _as_text(item: str | BaseModel | Mapping[str, object]) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, BaseModel):
        return item.model_dump_json()
    return json.dumps(dict(item), ensure_ascii=False)


def _result(
    role: Role, model: str, messages: Sequence[ChatMessage], text: str, json_mode: JsonMode
) -> LLMResult:
    # Rough token counts (about four characters per token) so usage reports have numbers.
    prompt_chars = sum(len(message.content) for message in messages)
    return LLMResult(
        text=text,
        model=model,
        role=role,
        prompt_tokens=max(1, prompt_chars // 4),
        completion_tokens=max(1, len(text) // 4),
        latency_ms=0,
        attempts=1,
        json_mode=json_mode,
    )


if TYPE_CHECKING:
    from app.llm.client import LLMClient

    _conforms: LLMClient = FakeLLM()
