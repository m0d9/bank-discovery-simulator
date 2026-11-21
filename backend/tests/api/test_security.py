"""Security hygiene: response headers and the CSP, and the request body limit."""

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

CSP = (
    "default-src 'self'; img-src 'self' data:; font-src 'self'; style-src 'self'; "
    "frame-ancestors 'none'"
)
MAX_BODY = 32 * 1024
JSON = {"content-type": "application/json"}
OTHER_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        ("GET", "/", 200),  # the SPA's index.html
        ("GET", "/interview/x", 200),  # a client route, served the same index.html
        ("GET", "/assets/app.js", 200),
        ("GET", "/api/health", 200),
        ("GET", "/api/nope", 404),  # an error envelope
        ("POST", "/api/sessions", 422),
    ],
)
def test_every_response_has_the_csp_and_the_security_headers(
    client: TestClient, method: str, path: str, status: int
) -> None:
    res = client.request(method, path)

    assert res.status_code == status
    assert res.headers["content-security-policy"] == CSP
    for name, value in OTHER_HEADERS.items():
        assert res.headers[name] == value, name


def test_the_api_docs_page_only_forbids_framing(client: TestClient) -> None:
    # Swagger UI needs its CDN and an inline script; the page has no user content.
    res = client.get("/api/docs")

    assert res.status_code == 200
    assert res.headers["content-security-policy"] == "frame-ancestors 'none'"
    assert res.headers["x-content-type-options"] == "nosniff"


def test_a_body_over_32_kb_gets_413_in_the_error_envelope(client: TestClient) -> None:
    res = client.post("/api/sessions", content=b"x" * (MAX_BODY + 1), headers=JSON)

    assert res.status_code == 413
    assert res.json() == {
        "error": {
            "code": "REQUEST_TOO_LARGE",
            "message_key": "errors.REQUEST_TOO_LARGE",
            "detail": f"the request body is larger than {MAX_BODY} bytes",
        }
    }
    assert res.headers["content-security-policy"] == CSP


def test_a_chunked_body_over_32_kb_is_refused_too(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(33):
            yield b"x" * 1024

    res = client.post("/api/sessions", content=chunks(), headers=JSON)

    assert "content-length" not in res.request.headers  # no declared length to go by
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "REQUEST_TOO_LARGE"


def test_a_body_of_exactly_32_kb_reaches_the_app(client: TestClient) -> None:
    empty = json.dumps({"client_id": "", "language": "en"})
    body = json.dumps({"client_id": "x" * (MAX_BODY - len(empty)), "language": "en"})
    assert len(body.encode()) == MAX_BODY

    res = client.post("/api/sessions", content=body, headers=JSON)

    assert res.status_code == 404
    assert res.json()["error"]["code"] == "UNKNOWN_CLIENT"
