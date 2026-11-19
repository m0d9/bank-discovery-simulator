"""A scripted OpenAI-compatible endpoint, served to the SDK through httpx2.MockTransport."""

import json
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

import httpx2

# A scripted reply: a response, an exception to raise (e.g. httpx2.ConnectError), or an
# async callable for replies that need to wait or inspect the request.
Reply = httpx2.Response | Exception | Callable[[httpx2.Request], Awaitable[httpx2.Response]]


def completion(
    content: str | None = "ok",
    *,
    finish_reason: str = "stop",
    prompt_tokens: int = 11,
    completion_tokens: int = 7,
    reasoning: str | None = None,
) -> httpx2.Response:
    """A successful chat completion."""
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if reasoning is not None:
        message["reasoning"] = reasoning
    return httpx2.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": "served-model",
            "choices": [{"index": 0, "finish_reason": finish_reason, "message": message}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        },
    )


def error(
    status: int,
    message: str = "error",
    *,
    code: str | None = None,
    headers: dict[str, str] | None = None,
) -> httpx2.Response:
    """An OpenAI-style error response."""
    body = {"error": {"message": message, "type": "invalid_request_error", "code": code}}
    return httpx2.Response(status, headers=headers, json=body)


def models(*ids: str) -> httpx2.Response:
    """A `GET /models` response listing `ids`."""
    data = [{"id": i, "object": "model", "created": 0, "owned_by": "test"} for i in ids]
    return httpx2.Response(200, json={"object": "list", "data": data})


class MockEndpoint:
    """Serves scripted replies to /chat/completions and /models, and records every request."""

    def __init__(self) -> None:
        self.chat_replies: deque[Reply] = deque()
        self.models_reply: Reply = models()
        self.requests: list[httpx2.Request] = []

    def queue(self, *replies: Reply) -> None:
        """Add replies for the next chat requests, in order."""
        self.chat_replies.extend(replies)

    @property
    def chat_requests(self) -> list[httpx2.Request]:
        return [r for r in self.requests if r.url.path.endswith("/chat/completions")]

    @property
    def chat_bodies(self) -> list[dict[str, Any]]:
        """JSON bodies of the chat requests, in order."""
        return [json.loads(r.content) for r in self.chat_requests]

    async def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if request.url.path.endswith("/chat/completions"):
            if not self.chat_replies:
                raise AssertionError("MockEndpoint: no scripted chat reply left")
            reply = self.chat_replies.popleft()
        elif request.url.path.endswith("/models"):
            reply = self.models_reply
        else:
            return error(404, f"unknown path {request.url.path}")
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, httpx2.Response):
            return reply
        return await reply(request)

    def http_client(self) -> httpx2.AsyncClient:
        """An httpx2 client whose transport is this endpoint, for AsyncOpenAI(http_client=...)."""
        return httpx2.AsyncClient(transport=httpx2.MockTransport(self.handle))
