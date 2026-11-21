"""ASGI middleware for every request: security headers.

A plain ASGI class rather than `BaseHTTPMiddleware`, so responses stream through untouched
apart from their headers.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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
