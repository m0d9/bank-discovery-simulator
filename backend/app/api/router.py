"""Aggregate API router, mounted under `/api`."""

from fastapi import APIRouter

from app.api import routes_content, routes_feedback, routes_health, routes_sessions

api_router = APIRouter()
api_router.include_router(routes_health.router)
api_router.include_router(routes_content.router)
api_router.include_router(routes_sessions.router)
api_router.include_router(routes_feedback.router)
