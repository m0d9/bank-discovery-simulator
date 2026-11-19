"""The model client contract, and its implementation for OpenAI-compatible endpoints."""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Literal, Protocol
from urllib.parse import urlsplit

import openai
from openai import AsyncOpenAI, Omit, omit
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.shared_params import ResponseFormatJSONSchema
from pydantic import BaseModel

from app.config import Settings
from app.llm.errors import (
    InvalidOutput,
    LLMError,
    ModelTimeout,
    ModelUnavailable,
    OutputTruncated,
    RateLimited,
    outcome_of,
)
from app.llm.json_output import (
    json_retry_instruction,
    parse_reply,
    schema_instruction,
    strip_reasoning,
)
from app.llm.roles import Role, resolve_model, role_timeout
from app.llm.types import ChatMessage, JsonMode, LLMResult
from app.llm.usage import LLMCallEvent, estimate_cost_usd
from app.telemetry.events import EventLogger, event_logger_for

if TYPE_CHECKING:
    import httpx2

logger = logging.getLogger(__name__)

_BACKOFF_BASE_S = 0.5
_JITTER_S = 0.25
_RETRY_AFTER_CAP_S = 5.0
# Docker's HEALTHCHECK allows /api/health 4 s in total, so listing models must answer sooner.
_LIST_MODELS_TIMEOUT_S = 3.0

_Param = Literal["reasoning_effort", "response_format"]


class LLMClient(Protocol):
    """What every model client offers. The app, scripts and evals depend only on this."""

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
        """Return the model's reply as plain text, with any reasoning removed."""
        ...

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
        """Return the reply parsed and validated as `schema`, plus the call's result."""
        ...

    async def list_models(self) -> list[str]:
        """Return the model ids the endpoint offers."""
        ...


@dataclass
class _Call:
    """Measurements for one logical call, across all the HTTP requests it makes."""

    role: Role
    model: str
    prompt_version: str | None
    json_mode: JsonMode = "none"
    attempts: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    started: float = field(default_factory=time.perf_counter)
    latency_ms: int = 0

    def add_usage(self, completion: ChatCompletion) -> None:
        if completion.usage is None:
            return
        self.prompt_tokens = (self.prompt_tokens or 0) + completion.usage.prompt_tokens
        self.completion_tokens = (self.completion_tokens or 0) + completion.usage.completion_tokens

    def stop(self) -> None:
        self.latency_ms = round((time.perf_counter() - self.started) * 1000)

    def result(self, text: str) -> LLMResult:
        return LLMResult(
            text=text,
            model=self.model,
            role=self.role,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            latency_ms=self.latency_ms,
            attempts=self.attempts,
            json_mode=self.json_mode,
        )


class _InvalidGeneration(Exception):
    """The server rejected its own JSON output (Groq's `json_validate_failed`)."""


class OpenAICompatClient:
    """`LLMClient` for any OpenAI-compatible Chat Completions endpoint, such as Ollama or Groq.

    Every request waits on one semaphore (LLM_MAX_CONCURRENCY). Timeouts, connection errors,
    429 and 5xx are retried with back-off; every call emits one `llm_call` event.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: "httpx2.AsyncClient | None" = None,
        events: EventLogger | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._settings = settings
        self._base_url = settings.LLM_BASE_URL
        # Retrying is our job (typed errors, telemetry, Retry-After cap), so the SDK must not.
        self._sdk = AsyncOpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY.get_secret_value(),
            max_retries=0,
            http_client=http_client,
        )
        self._semaphore = asyncio.Semaphore(settings.LLM_MAX_CONCURRENCY)
        self._events = events if events is not None else event_logger_for(settings.DATA_DIR)
        self._sleep = sleep
        self._jitter = jitter
        # (base_url, model, parameter) triples the server rejected; one client per process.
        self._unsupported: set[tuple[str, str, _Param]] = set()

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
        """Return the model's reply as plain text, with any reasoning removed.

        Raises OutputTruncated when the model used all of `max_tokens` without any visible text.
        """
        call = self._start(role, model, prompt_version, json_mode="none")
        try:
            completion = await self._complete(
                call, messages, max_tokens=max_tokens, temperature=temperature, schema=None
            )
            text, finish_reason = _reply(completion)
            if not text and finish_reason == "length":
                raise OutputTruncated("the model used all of max_tokens before answering")
        except BaseException as exc:
            await self._finish(call, exc)
            raise
        await self._finish(call, None)
        return call.result(text)

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
        """Return the reply parsed and validated as `schema`, plus the call's result.

        Asks for JSON through `response_format`, or through the prompt if the server rejects
        that. An unusable reply gets one retry: with max_tokens doubled if it was cut off,
        otherwise with a note about the problem. Raises InvalidOutput if that fails too.
        """
        call = self._start(role, model, prompt_version, json_mode="schema")
        if not self._supports(call.model, "response_format"):
            call.json_mode = "prompt"
        try:
            value, text = await self._json_attempts(call, messages, schema, max_tokens, temperature)
        except BaseException as exc:
            await self._finish(call, exc)
            raise
        await self._finish(call, None)
        return value, call.result(text)

    async def list_models(self) -> list[str]:
        """Return the endpoint's model ids.

        Skips the semaphore and retries: /api/health must answer quickly even while a long
        coach call holds the only slot.
        """
        try:
            page = await self._sdk.models.list(timeout=_LIST_MODELS_TIMEOUT_S)
        except openai.APIError as exc:
            raise _classify(exc)[0] from exc
        return [entry.id for entry in page.data]

    # --- one logical call -------------------------------------------------------------------

    def _start(
        self, role: Role, model: str | None, prompt_version: str | None, *, json_mode: JsonMode
    ) -> _Call:
        return _Call(
            role=role,
            model=resolve_model(role, model, settings=self._settings),
            prompt_version=prompt_version,
            json_mode=json_mode,
        )

    async def _finish(self, call: _Call, error: BaseException | None) -> None:
        call.stop()
        if isinstance(error, asyncio.CancelledError):
            return  # the caller went away; nothing useful to record
        if error is None:
            outcome = "ok"
        elif isinstance(error, LLMError):
            outcome = outcome_of(error)
        else:
            outcome = LLMError.code
        event = LLMCallEvent(
            role=call.role,
            model=call.model,
            prompt_tokens=call.prompt_tokens,
            completion_tokens=call.completion_tokens,
            latency_ms=call.latency_ms,
            attempts=call.attempts,
            outcome=outcome,
            json_mode=call.json_mode,
            est_cost_usd=estimate_cost_usd(
                call.prompt_tokens, call.completion_tokens, self._settings
            ),
            prompt_version=call.prompt_version,
        )
        await self._events.emit("llm_call", **event.model_dump(mode="json"))
        if outcome != "ok":
            logger.warning(
                "model call failed",
                extra={
                    "role": call.role.value,
                    "model": call.model,
                    "outcome": outcome,
                    "attempts": call.attempts,
                },
            )

    async def _json_attempts[T: BaseModel](
        self,
        call: _Call,
        messages: Sequence[ChatMessage],
        schema: type[T],
        max_tokens: int,
        temperature: float,
    ) -> tuple[T, str]:
        conversation = list(messages)
        budget = max_tokens
        retried = False
        while True:
            text, truncated = "", False
            try:
                completion = await self._complete(
                    call, conversation, max_tokens=budget, temperature=temperature, schema=schema
                )
            except _InvalidGeneration:
                problem = "the server could not validate the JSON it generated"
            else:
                text, finish_reason = _reply(completion)
                truncated = finish_reason == "length"
                try:
                    return parse_reply(text, schema), text
                except ValueError as exc:  # only parse/validation problems are retried
                    problem = str(exc)
            if retried:
                error = OutputTruncated if truncated else InvalidOutput
                raise error(f"unusable JSON after one retry: {problem}", raw_text=text)
            retried = True
            if truncated:
                # Cut off by the token limit (often hidden reasoning): same request, more room.
                budget *= 2
            else:
                conversation.append(
                    ChatMessage(role="user", content=json_retry_instruction(problem))
                )

    # --- one completion, adapting to what the server supports -------------------------------

    def _supports(self, model: str, param: _Param) -> bool:
        return (self._base_url, model, param) not in self._unsupported

    async def _complete(
        self,
        call: _Call,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int,
        temperature: float,
        schema: type[BaseModel] | None,
    ) -> ChatCompletion:
        while True:
            send_reasoning = self._settings.LLM_DISABLE_THINKING and self._supports(
                call.model, "reasoning_effort"
            )
            send_schema = schema is not None and call.json_mode == "schema"
            payload = list(messages)
            if schema is not None and call.json_mode == "prompt":
                payload = _with_instruction(payload, schema_instruction(schema))
            try:
                return await self._send(
                    call,
                    messages=[_to_sdk(message) for message in payload],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    reasoning_effort="none" if send_reasoning else omit,
                    response_format=_json_schema_format(schema)
                    if send_schema and schema is not None
                    else omit,
                )
            except openai.BadRequestError as exc:
                if send_schema and exc.code == "json_validate_failed":
                    raise _InvalidGeneration from exc
                rejected = _rejected_param(
                    exc, reasoning_sent=send_reasoning, schema_sent=send_schema
                )
                if rejected is None:
                    raise _classify(exc)[0] from exc
                self._unsupported.add((self._base_url, call.model, rejected))
                logger.info(
                    "endpoint rejected a parameter; continuing without it",
                    extra={"param": rejected, "model": call.model},
                )
                if rejected == "response_format":
                    call.json_mode = "prompt"

    async def _send(
        self,
        call: _Call,
        *,
        messages: list[ChatCompletionMessageParam],
        max_tokens: int,
        temperature: float,
        reasoning_effort: Literal["none"] | Omit,
        response_format: ResponseFormatJSONSchema | Omit,
    ) -> ChatCompletion:
        """Send one request, retrying transient failures. A 400 is re-raised untouched."""
        timeout = role_timeout(call.role, self._settings)
        retry = 0
        while True:
            call.attempts += 1
            try:
                async with self._semaphore:
                    completion = await self._sdk.chat.completions.create(
                        model=call.model,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        reasoning_effort=reasoning_effort,
                        response_format=response_format,
                        timeout=timeout,
                    )
            except openai.BadRequestError:
                raise
            except openai.APIError as exc:
                error, retryable, retry_after = _classify(exc)
                if not retryable or retry >= self._settings.LLM_MAX_RETRIES:
                    raise error from exc
                await self._sleep(self._backoff(retry, retry_after))
                retry += 1
                continue
            call.add_usage(completion)
            return completion

    def _backoff(self, retry: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return min(retry_after, _RETRY_AFTER_CAP_S)
        return _BACKOFF_BASE_S * 2.0**retry + self._jitter() * _JITTER_S


def endpoint_host(base_url: str) -> str:
    """Return the endpoint's `host[:port]`, never its credentials or path."""
    parts = urlsplit(base_url)
    host = parts.hostname or ""
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    try:
        port = parts.port
    except ValueError:
        port = None
    return f"{host}:{port}" if port else host


def _reply(completion: ChatCompletion) -> tuple[str, str | None]:
    """Return the visible reply text and the finish reason.

    A separate `reasoning` field, which some servers add, is deliberately ignored.
    """
    if not completion.choices:
        raise InvalidOutput("the endpoint returned no choices")
    choice = completion.choices[0]
    return strip_reasoning(choice.message.content or ""), choice.finish_reason


def _to_sdk(message: ChatMessage) -> ChatCompletionMessageParam:
    if message.role == "system":
        return ChatCompletionSystemMessageParam(role="system", content=message.content)
    if message.role == "user":
        return ChatCompletionUserMessageParam(role="user", content=message.content)
    return ChatCompletionAssistantMessageParam(role="assistant", content=message.content)


def _with_instruction(messages: list[ChatMessage], instruction: str) -> list[ChatMessage]:
    """Append `instruction` to the first system message, or add a system message for it."""
    for index, message in enumerate(messages):
        if message.role == "system":
            updated = ChatMessage(role="system", content=f"{message.content}\n\n{instruction}")
            return [*messages[:index], updated, *messages[index + 1 :]]
    return [ChatMessage(role="system", content=instruction), *messages]


def _json_schema_format(schema: type[BaseModel]) -> ResponseFormatJSONSchema:
    return {
        "type": "json_schema",
        "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()},
    }


def _rejected_param(
    exc: openai.BadRequestError, *, reasoning_sent: bool, schema_sent: bool
) -> _Param | None:
    """Return the parameter a 400 complains about, if it is one we can drop."""
    said = f"{exc.message} {exc.param or ''}".lower()
    if reasoning_sent and "reasoning" in said:
        return "reasoning_effort"
    if schema_sent and ("response_format" in said or "json_schema" in said):
        return "response_format"
    return None


def _classify(exc: openai.APIError) -> tuple[LLMError, bool, float | None]:
    """Map an SDK error to (typed error, whether to retry, Retry-After seconds).

    Details are fixed strings: server messages can echo request text, so they are not kept.
    """
    if isinstance(exc, openai.APITimeoutError):
        return ModelTimeout("the model did not answer in time"), True, None
    if isinstance(exc, openai.APIConnectionError):
        return ModelUnavailable("cannot reach the model endpoint", reason="unreachable"), True, None
    if isinstance(exc, openai.APIStatusError):
        status = exc.status_code
        http = f"HTTP {status}"
        if status == 429:
            return RateLimited(f"the endpoint is rate limiting ({http})"), True, _retry_after(exc)
        if status >= 500:
            failed = ModelUnavailable(f"the endpoint failed ({http})", reason="server_error")
            return failed, True, _retry_after(exc)
        if status == 404:
            missing = ModelUnavailable(f"model or path not found ({http})", reason="not_found")
            return missing, False, None
        if status in (401, 403):
            denied = ModelUnavailable(f"the endpoint rejected the API key ({http})", reason="auth")
            return denied, False, None
        return LLMError(f"the endpoint rejected the request ({http})"), False, None
    return LLMError("unexpected response from the model endpoint"), False, None


def _retry_after(exc: openai.APIStatusError) -> float | None:
    """Seconds the server asked us to wait, from `retry-after-ms` or `Retry-After`."""
    headers: Mapping[str, str] = exc.response.headers
    millis = headers.get("retry-after-ms")
    if millis:
        try:
            return max(0.0, float(millis) / 1000)
        except ValueError:
            pass
    value = headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, (when - datetime.now(UTC)).total_seconds())
