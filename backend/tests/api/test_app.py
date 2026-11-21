import httpx
import pytest
from fastapi.testclient import TestClient


def test_health_ok(client: TestClient) -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert isinstance(body["version"], str) and body["version"]


def test_openapi_json_under_api(client: TestClient) -> None:
    res = client.get("/api/openapi.json")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    assert "/api/health" in res.json()["paths"]


def test_docs_under_api(client: TestClient) -> None:
    res = client.get("/api/docs")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]


def test_spa_fallback_serves_index(client: TestClient) -> None:
    res = client.get("/interview/x")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "<title>spa</title>" in res.text


def test_spa_serves_assets(client: TestClient) -> None:
    res = client.get("/assets/app.js")
    assert res.status_code == 200
    assert "console.log" in res.text


API_PATHS = ("/api", "/api/", "/api/nope", "/api/nope/deeper", "/api?x=1")


def assert_not_found_envelope(res: httpx.Response) -> None:
    assert res.status_code == 404, res.url
    assert res.headers["content-type"].startswith("application/json"), res.url
    error = res.json()["error"]
    assert (error["code"], error["message_key"]) == ("NOT_FOUND", "errors.NOT_FOUND"), res.url


@pytest.mark.parametrize("path", API_PATHS)
def test_unknown_api_paths_get_the_error_envelope_never_the_spa(
    client: TestClient, path: str
) -> None:
    assert_not_found_envelope(client.get(path))


def test_unknown_api_paths_get_the_envelope_for_any_method(client: TestClient) -> None:
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert_not_found_envelope(client.request(method, "/api/nope"))


def test_spa_does_not_escape_dist(client: TestClient) -> None:
    res = client.get("/..%2F..%2Fetc%2Fpasswd")
    assert res.status_code == 200
    assert "<title>spa</title>" in res.text


def test_dev_mode_without_dist(dev_client: TestClient) -> None:
    res = dev_client.get("/")
    assert res.status_code == 200
    assert "note" in res.json()
    assert dev_client.get("/api/health").status_code == 200
    for path in (*API_PATHS, "/interview/x"):
        assert_not_found_envelope(dev_client.get(path))
