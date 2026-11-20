"""Content CLI.

uv run python -m app.content validate   # check every file; exit 1 on any error
uv run python -m app.content schema     # write content/schema/*.schema.json for editors
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.content.loader import ContentValidationError
from app.content.models import Bank, Client, Product
from app.content.registry import load_registry

SCHEMA_MODELS: dict[str, type[BaseModel]] = {"bank": Bank, "product": Product, "client": Client}


def render_schemas() -> dict[str, str]:
    """The JSON Schema text for each kind of content file, keyed by file name."""
    return {
        f"{kind}.schema.json": json.dumps(model.model_json_schema(), indent=2) + "\n"
        for kind, model in SCHEMA_MODELS.items()
    }


def validate(content_dir: Path) -> int:
    """Print `✓ N products, M clients`, or every error (one per line) and return 1."""
    try:
        registry = load_registry(content_dir)
    except ContentValidationError as exc:
        for message in exc.messages:
            _say(message, error=True)
        return 1
    products = _count(len(registry.list_products()), "product")
    clients = _count(len(registry.list_clients()), "client")
    _say(f"✓ {products}, {clients}")
    return 0


def write_schemas(schema_dir: Path) -> int:
    """Write one JSON Schema per kind of content file into `schema_dir`."""
    schema_dir.mkdir(parents=True, exist_ok=True)
    for name, text in render_schemas().items():
        (schema_dir / name).write_text(text, encoding="utf-8")
        _say(f"wrote {schema_dir.name}/{name}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments, run the command and return the exit code."""
    parser = argparse.ArgumentParser(
        prog="python -m app.content",
        description="Validate the content YAML, or export its JSON Schemas for editors.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate", help="check every content file; exit 1 if anything is wrong")
    commands.add_parser("schema", help="write content/schema/{bank,product,client}.schema.json")
    args = parser.parse_args(argv)
    try:
        settings = get_settings()
    except ValidationError as exc:
        # Name the settings only: their values may include the API key.
        names = ", ".join(sorted({str(error["loc"][0]) for error in exc.errors()}))
        _say(
            f"Settings are missing or invalid ({names}). Copy .env.example to .env: only "
            "LLM_BASE_URL, LLM_API_KEY and LLM_MODEL are required.",
            error=True,
        )
        return 2
    if args.command == "validate":
        return validate(settings.CONTENT_DIR)
    return write_schemas(settings.CONTENT_DIR / "schema")


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


def _say(line: str, *, error: bool = False) -> None:
    # Console output of a CLI, not logging.
    stream = sys.stderr if error else sys.stdout
    stream.write(line + "\n")
    stream.flush()


if __name__ == "__main__":
    sys.exit(main())
