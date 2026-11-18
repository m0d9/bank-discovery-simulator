"""Health endpoint. M1 extends it with model reachability."""

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter

from app.api.dto import HealthOut

router = APIRouter(tags=["health"])


def _app_version() -> str:
    try:
        return version("bank-discovery-simulator")
    except PackageNotFoundError:
        return "0.0.0"


@router.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    """Report that the server is up."""
    return HealthOut(status="ok", version=_app_version())
