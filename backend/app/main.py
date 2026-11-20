"""FastAPI application factory: API under `/api`, built SPA everywhere else."""

import logging
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.config import Settings, get_settings
from app.content import ContentStore, ContentValidationError
from app.logging_setup import configure_logging

logger = logging.getLogger(__name__)


def _api_not_found_router() -> APIRouter:
    # Registered after all real API routes so unknown /api paths get JSON, never index.html.
    router = APIRouter()

    @router.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )
    async def api_not_found(path: str) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "NOT_FOUND",
                    "message_key": "errors.NOT_FOUND",
                    "detail": f"/api/{path}",
                }
            },
        )

    return router


def _mount_spa(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")
    dist_root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path == "api":
            raise HTTPException(status_code=404)
        # Serve real top-level files (favicon etc.); fall back to index.html for client routes.
        candidate = (dist_root / path).resolve()
        if path and candidate.is_relative_to(dist_root) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)


def _mount_dev_note(app: FastAPI) -> None:
    @app.get("/", include_in_schema=False)
    async def dev_note() -> JSONResponse:
        return JSONResponse(
            {
                "note": "Frontend build not found. In dev, open the Vite server "
                "(http://localhost:5173); the API is under /api."
            }
        )

    @app.get("/{path:path}", include_in_schema=False)
    async def not_found(path: str) -> JSONResponse:
        raise HTTPException(status_code=404)


def _open_content(content_dir: Path) -> ContentStore:
    try:
        return ContentStore(content_dir)
    except ContentValidationError as exc:
        # Fail fast: there's no earlier good version to serve instead.
        logger.error(
            "Content is invalid; fix the files and restart",
            extra={"content_errors": exc.messages},
        )
        raise


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app. Pass `settings` to override the cached defaults (tests).

    Raises `ContentValidationError` if the content is invalid: the app won't start without it.
    """
    injected = settings
    settings = settings or get_settings()
    configure_logging(secrets=[settings.LLM_API_KEY.get_secret_value()])
    content_store = _open_content(settings.CONTENT_DIR)

    app = FastAPI(
        title="Bank Client Discovery Simulator",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.content_store = content_store
    if injected is not None:
        # Routes read settings through Depends(get_settings); make them see the injected ones.
        app.dependency_overrides[get_settings] = lambda: injected
    app.include_router(api_router, prefix="/api")
    app.include_router(_api_not_found_router(), prefix="/api")

    if (settings.FRONTEND_DIST / "index.html").is_file():
        _mount_spa(app, settings.FRONTEND_DIST)
    else:
        _mount_dev_note(app)
    return app


app = create_app()
