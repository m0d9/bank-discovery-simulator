from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def dist_dir(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>spa</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('x')", encoding="utf-8")
    return dist


@pytest.fixture
def client(dist_dir: Path) -> Iterator[TestClient]:
    app = create_app(Settings(FRONTEND_DIST=dist_dir))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def dev_client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(Settings(FRONTEND_DIST=tmp_path / "missing"))
    with TestClient(app) as c:
        yield c
