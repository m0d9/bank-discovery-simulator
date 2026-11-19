import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.content import __main__ as cli
from tests.conftest import SettingsFactory
from tests.content_factory import CLIENT, ContentDir, client_data


def test_validate_prints_the_counts_and_exits_0(
    content: ContentDir, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.validate(content.root) == 0
    assert capsys.readouterr().out == "✓ 2 products, 1 client\n"


def test_validate_prints_one_line_per_error_and_exits_1(
    content: ContentDir, capsys: pytest.CaptureFixture[str]
) -> None:
    content.write(f"clients/{CLIENT}.yaml", client_data(difficulty="expert"))

    assert cli.validate(content.root) == 1

    out, err = capsys.readouterr()
    assert out == ""
    assert err.splitlines() == [
        "content/clients/test-client.yaml › difficulty: Input should be 'easy', 'medium' or 'hard'"
    ]


def test_schema_writes_one_file_per_kind(tmp_path: Path) -> None:
    assert cli.write_schemas(tmp_path / "schema") == 0

    written = sorted(path.name for path in (tmp_path / "schema").iterdir())
    assert written == ["bank.schema.json", "client.schema.json", "product.schema.json"]
    client_schema = json.loads((tmp_path / "schema" / "client.schema.json").read_text("utf-8"))
    assert client_schema["additionalProperties"] is False
    assert "hidden_facts" in client_schema["properties"]


@pytest.mark.parametrize("command", ["validate", "schema"])
def test_main_reads_the_content_folder_from_settings(
    command: str,
    content: ContentDir,
    settings_factory: SettingsFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: settings_factory(CONTENT_DIR=content.root))

    assert cli.main([command]) == 0
    if command == "schema":
        assert (content.root / "schema" / "product.schema.json").is_file()


def test_main_explains_missing_settings_without_showing_values(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_settings() -> Settings:
        return Settings(_env_file=None, LLM_API_KEY="sk-should-not-appear")  # type: ignore[call-arg]

    monkeypatch.setattr(cli, "get_settings", no_settings)
    with pytest.raises(ValidationError):
        no_settings()

    assert cli.main(["validate"]) == 2

    err = capsys.readouterr().err
    assert "LLM_BASE_URL, LLM_MODEL" in err and ".env.example" in err
    assert "sk-should-not-appear" not in err
