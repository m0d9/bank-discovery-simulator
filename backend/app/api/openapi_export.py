"""Write the API contract for the frontend (`make openapi`).

    uv run python -m app.api.openapi_export

Writes `frontend/src/api/openapi.json`, from `app.openapi()`, and
`frontend/src/api/error-codes.json`, every `code` the error envelope can carry. Building the
app needs the three LLM_* settings. Without a `.env`, placeholders work, and no model is
contacted.
"""

import json
import sys
from pathlib import Path

from fastapi import FastAPI
from pydantic import ValidationError

from app.api.errors import ERROR_CODES
from app.config import get_settings

FRONTEND_API_DIR = Path(__file__).resolve().parents[3] / "frontend" / "src" / "api"


def render_contract(app: FastAPI) -> dict[str, str]:
    """The text of each contract file, keyed by file name."""
    return {
        "openapi.json": json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n",
        "error-codes.json": json.dumps(list(ERROR_CODES), indent=2) + "\n",
    }


def main() -> int:
    """Write the contract files and return the exit code."""
    try:
        get_settings()
    except ValidationError as exc:
        # Name the settings only: their values may include the API key.
        names = ", ".join(sorted({str(error["loc"][0]) for error in exc.errors()}))
        _say(
            f"Settings are missing or invalid ({names}). Copy .env.example to .env, or pass "
            "placeholders: LLM_BASE_URL=http://localhost/v1 LLM_API_KEY=placeholder "
            "LLM_MODEL=placeholder make openapi",
            error=True,
        )
        return 2
    from app.main import app  # imported only now: building the app needs the settings

    FRONTEND_API_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in render_contract(app).items():
        (FRONTEND_API_DIR / name).write_text(text, encoding="utf-8")
        _say(f"wrote frontend/src/api/{name}")
    return 0


def _say(line: str, *, error: bool = False) -> None:
    # Console output of a CLI, not logging.
    stream = sys.stderr if error else sys.stdout
    stream.write(line + "\n")
    stream.flush()


if __name__ == "__main__":
    sys.exit(main())
