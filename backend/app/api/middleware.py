"""ASGI middleware for every request: security headers, and a size limit on request bodies.

Both are plain ASGI classes rather than `BaseHTTPMiddleware`, so responses stream through
untouched apart from their headers.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import error_response

CSP = (
    "default-src 'self'; img-src 'self' data:; font-src 'self'; style-src 'self'; "
    "frame-ancestors 'none'"
)
# Swagger UI loads its script and styles from a CDN and starts from an inline script, so the
# app's policy would leave the page blank. The page is static, with no user content, so it
# only forbids framing.
DOCS_CSP = "frame-ancestors 'none'"
DOCS_PATH = "/api/docs"
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
MAX_BODY_BYTES = 32 * 1024


class SecurityHeadersMiddleware:
    """Adds the Content-Security-Policy and the other security headers to every response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        csp = DOCS_CSP if scope["path"] == DOCS_PATH else CSP

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Content-Security-Policy"] = csp
                for name, value in SECURITY_HEADERS.items():
                    headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodyLimitMiddleware:
    """Answers 413 (`REQUEST_TOO_LARGE`, in the error envelope) to a body over `max_bytes`.

    A declared `Content-Length` over the limit is refused before anything is read. Any other
    body is read up to the limit before the app sees it, so a chunked upload can't get past.
    """

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if _declared_length(scope) > self.max_bytes:
            await self._too_large(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] != "http.request":
                return  # the client went away before sending the whole body
            body += message.get("body", b"")
            if len(body) > self.max_bytes:
                await self._too_large(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay() -> Message:
            # The body once, as one message; after that, the client's own messages (such as
            # a disconnect while a response streams).
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)

    async def _too_large(self, scope: Scope, receive: Receive, send: Send) -> None:
        detail = f"the request body is larger than {self.max_bytes} bytes"
        await error_response("REQUEST_TOO_LARGE", detail)(scope, receive, send)


def _declared_length(scope: Scope) -> int:
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return 0  # the server rejects a malformed length before the app runs
    return 0
