"""Security hygiene: response headers and the CSP."""

import pytest
from fastapi.testclient import TestClient

CSP = (
    "default-src 'self'; img-src 'self' data:; font-src 'self'; style-src 'self'; "
    "frame-ancestors 'none'"
)
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
