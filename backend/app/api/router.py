"""Aggregate API router, mounted under `/api`."""

from fastapi import APIRouter

from app.api import routes_content, routes_health

api_router = APIRouter()
api_router.include_router(routes_health.router)
api_router.include_router(routes_content.router)
