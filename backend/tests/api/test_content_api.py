import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.dto import ProductDTO
from app.content import ContentValidationError
from app.content import store as store_module
from app.llm import llm_dep
from app.llm.fake import FakeLLM
from app.main import create_app
from tests.conftest import SettingsFactory
from tests.content_factory import ALPHA, CLIENT, SECRET_CASH_GAP, ContentDir, client_data

BROKEN = "content/clients/test-client.yaml › difficulty: Input should be 'easy', 'medium' or 'hard'"


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """The content store's clock; move it 2 s on to let the store look at the files again."""
    now = [1000.0]
    monkeypatch.setattr(store_module, "_now", lambda: now[0])
    return now


@pytest.fixture
def api(
    content: ContentDir,
    clock: list[float],
    settings_factory: SettingsFactory,
    fake_llm: FakeLLM,
    tmp_path: Path,
) -> Iterator[TestClient]:
    """The app serving the sample content from a temporary folder."""
    settings = settings_factory(CONTENT_DIR=content.root, FRONTEND_DIST=tmp_path / "missing")
    app = create_app(settings)
    app.dependency_overrides[llm_dep] = lambda: fake_llm
    with TestClient(app) as test_client:
        yield test_client


def test_bank(api: TestClient) -> None:
    assert api.get("/api/bank").json() == {
        "name": {"en": "Test Bank", "ar": "بنك الاختبار"},
        "tagline": {"en": "Tested first", "ar": None},
        "disclaimer": {"en": "Fictional bank for tests.", "ar": None},
        "currency": "QAR",
    }


def test_clients_returns_public_cards_only(api: TestClient) -> None:
    assert api.get("/api/clients").json() == [
        {
            "id": CLIENT,
            "segment": "sme",
            "difficulty": "easy",
            "name": {"en": "Test Client", "ar": "عميل الاختبار"},
            "headline": {"en": "Owns a small test company", "ar": None},
        }
    ]


def test_products_show_the_catalogue_fields_but_not_the_client_view(api: TestClient) -> None:
    products = api.get("/api/products").json()

    assert [product["id"] for product in products] == [ALPHA, "beta-deposit"]
    assert set(products[0]) == set(ProductDTO.model_fields)
    assert "client_view" not in products[0]
    assert products[0]["features"] == [
        {"en": "Fast approval", "ar": None},
        {"en": "Flexible limit", "ar": None},
    ]
    assert products[0]["pricing"] == {"en": "Interest of 5% a year (fictional)", "ar": None}


def test_the_real_content_is_served(client: TestClient) -> None:
    assert client.get("/api/bank").json()["name"] == {"en": "Al Murjan Bank", "ar": "بنك المرجان"}
    assert [card["id"] for card in client.get("/api/clients").json()] == [
        "fatima-al-sulaiti",
        "rajesh-menon",
        "ahmed-hassan",
        "noura-al-kuwari",
    ]
    assert len(client.get("/api/products").json()) == 8


def test_an_edited_headline_shows_on_a_later_request(
    api: TestClient, content: ContentDir, clock: list[float]
) -> None:
    data = client_data()
    data["card"]["headline"] = "Now runs two companies"
    content.write(f"clients/{CLIENT}.yaml", data)

    assert api.get("/api/clients").json()[0]["headline"]["en"] == "Owns a small test company"
    clock[0] += 2
    assert api.get("/api/clients").json()[0]["headline"]["en"] == "Now runs two companies"


def test_health_reports_valid_content(api: TestClient) -> None:
    assert api.get("/api/health").json()["content"] == {"ok": True, "errors": []}


def test_a_broken_file_keeps_the_last_good_content_and_health_reports_it(
    api: TestClient, content: ContentDir, clock: list[float]
) -> None:
    api.get("/api/health")  # fills the 30-second model cache
    content.write(f"clients/{CLIENT}.yaml", client_data(difficulty="expert"))
    clock[0] += 2

    health = api.get("/api/health").json()
    assert health["status"] == "ok"  # the models are fine; only content.ok changes
    assert health["content"] == {"ok": False, "errors": [BROKEN]}
    assert api.get("/api/clients").json()[0]["difficulty"] == "easy"

    content.write(f"clients/{CLIENT}.yaml", client_data(difficulty="hard"))
    clock[0] += 2
    assert api.get("/api/health").json()["content"] == {"ok": True, "errors": []}
    assert api.get("/api/clients").json()[0]["difficulty"] == "hard"


def test_invalid_content_stops_the_app_from_starting(
    content: ContentDir,
    settings_factory: SettingsFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    broken = client_data(difficulty="expert")
    broken["hidden_facts"][0]["importance"] = SECRET_CASH_GAP
    content.write(f"clients/{CLIENT}.yaml", broken)

    with pytest.raises(ContentValidationError):
        create_app(settings_factory(CONTENT_DIR=content.root))

    logged = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    [record] = [entry for entry in logged if entry["logger"] == "app.main"]
    assert record["level"] == "ERROR"
    assert BROKEN in record["content_errors"]
    assert SECRET_CASH_GAP not in json.dumps(record)
