import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.api import openapi_export
from app.api.errors import ERROR_CODES
from app.config import Settings
from app.main import create_app
from tests.conftest import SettingsFactory


def test_the_committed_contract_files_are_current(
    settings_factory: SettingsFactory, tmp_path: Path
) -> None:
    app = create_app(settings_factory(FRONTEND_DIST=tmp_path / "missing"))

    for name, text in openapi_export.render_contract(app).items():
        committed = (openapi_export.FRONTEND_API_DIR / name).read_text(encoding="utf-8")
        assert committed == text, f"frontend/src/api/{name} is out of date: run `make openapi`"


def test_the_error_code_list_is_every_code_the_envelope_can_carry(
    settings_factory: SettingsFactory, tmp_path: Path
) -> None:
    app = create_app(settings_factory(FRONTEND_DIST=tmp_path / "missing"))
    codes = json.loads(openapi_export.render_contract(app)["error-codes.json"])
    assert codes == list(ERROR_CODES)
    assert "INTERNAL_ERROR" in codes and "NOT_FOUND" in codes


def test_main_writes_both_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openapi_export, "FRONTEND_API_DIR", tmp_path / "api")

    assert openapi_export.main() == 0

    written = json.loads((tmp_path / "api" / "openapi.json").read_text(encoding="utf-8"))
    assert "/api/sessions" in written["paths"]
    assert (tmp_path / "api" / "error-codes.json").is_file()


def test_main_explains_missing_settings_without_showing_values(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_settings() -> Settings:
        return Settings(_env_file=None, LLM_API_KEY="sk-should-not-appear")  # type: ignore[call-arg]

    monkeypatch.setattr(openapi_export, "get_settings", no_settings)
    with pytest.raises(ValidationError):
        no_settings()

    assert openapi_export.main() == 2

    err = capsys.readouterr().err
    assert "LLM_BASE_URL, LLM_MODEL" in err and "placeholder" in err
    assert "sk-should-not-appear" not in err
