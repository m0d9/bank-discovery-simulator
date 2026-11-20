"""Feedback on a wrapped-up interview, and the Markdown export of a session."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.dto import FeedbackDTO
from app.api.errors import error_responses
from app.api.mappers import feedback_dto
from app.api.routes_sessions import get_session_store
from app.coaching import CoachCache, FeedbackService
from app.config import Settings, get_settings
from app.llm import LLMClient, llm_dep
from app.simulation import Language, SessionStore
from app.telemetry.events import event_logger_for

router = APIRouter(prefix="/sessions", tags=["feedback"])


def get_coach_cache(request: Request) -> CoachCache:
    """FastAPI dependency: the coach cache that `create_app` attached to the app."""
    cache = request.app.state.coach_cache
    if not isinstance(cache, CoachCache):
        raise RuntimeError("the app has no coach cache; build it with create_app()")
    return cache


def get_feedback_service(
    store: Annotated[SessionStore, Depends(get_session_store)],
    llm: Annotated[LLMClient, Depends(llm_dep)],
    settings: Annotated[Settings, Depends(get_settings)],
    cache: Annotated[CoachCache, Depends(get_coach_cache)],
) -> FeedbackService:
    """FastAPI dependency: the feedback service for this request (it holds no state)."""
    return FeedbackService(
        store=store, llm=llm, events=event_logger_for(settings.DATA_DIR), cache=cache
    )


Service = Annotated[FeedbackService, Depends(get_feedback_service)]


@router.post(
    "/{session_id}/feedback",
    response_model=FeedbackDTO,
    responses=error_responses(
        "SESSION_NOT_FOUND", "INVALID_STATE", "INVALID_INPUT", "INTERNAL_ERROR"
    ),
)
async def create_feedback(
    session_id: str,
    lang: Annotated[Language, Query(description="The language of the coach's report.")],
    service: Service,
) -> FeedbackDTO:
    """The analysis and the AI coach's report, once the interview is wrapped up.

    The first call can take a minute while the coach writes. Calling again with the same
    language returns the same report at once. If the coach is unavailable, `report` is null
    and `degraded` true: the analysis is still accurate, and calling again retries the coach.
    """
    session, feedback = await service.feedback(session_id, lang)
    return feedback_dto(session, feedback)


@router.get(
    "/{session_id}/export",
    response_class=Response,
    responses={
        200: {
            "description": "The session as a Markdown file, sent as an attachment.",
            "content": {"text/markdown": {"schema": {"type": "string"}}},
        },
        **error_responses("SESSION_NOT_FOUND", "INVALID_INPUT", "INTERNAL_ERROR"),
    },
)
async def export_session(
    session_id: str,
    service: Service,
    file_format: Annotated[Literal["md"], Query(alias="format")] = "md",
) -> Response:
    """Download the session: the transcript and the wrap-up, plus, once feedback exists, the
    analysis, the coach's feedback and the client's full profile."""
    export = service.export(session_id)
    return Response(
        content=export.text,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={export.filename}"},
    )
