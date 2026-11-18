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


def test_unknown_api_path_is_json_404(client: TestClient) -> None:
    for path in ("/api/nope", "/api/nope/deeper", "/api"):
        res = client.get(path)
        assert res.status_code == 404, path
        assert res.headers["content-type"].startswith("application/json"), path
    assert client.get("/api/nope").json()["error"]["code"] == "NOT_FOUND"
    assert client.post("/api/nope").status_code == 404


def test_spa_does_not_escape_dist(client: TestClient) -> None:
    res = client.get("/..%2F..%2Fetc%2Fpasswd")
    assert res.status_code == 200
    assert "<title>spa</title>" in res.text


def test_dev_mode_without_dist(dev_client: TestClient) -> None:
    res = dev_client.get("/")
    assert res.status_code == 200
    assert "note" in res.json()
    assert dev_client.get("/api/health").status_code == 200
    assert dev_client.get("/api/nope").status_code == 404
