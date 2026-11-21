"""Interview sessions: start one, send messages, wrap up, read the transcript, delete it."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.dto import (
    CreateSessionDTO,
    MessageResultDTO,
    SessionCreatedDTO,
    SessionPublicDTO,
    StudentMessageDTO,
    WrapUpDTO,
)
from app.api.errors import error_responses
from app.api.mappers import message_result_dto, session_created_dto, session_public_dto
from app.api.throttle import throttle_messages
from app.config import Settings, get_settings
from app.content import ContentRegistry, get_registry
from app.llm import LLMClient, llm_dep
from app.simulation import InterviewService, Recommendation, SessionStore, WrapUp
from app.telemetry.events import event_logger_for

router = APIRouter(prefix="/sessions", tags=["sessions"])

_MODEL_ERRORS = (
    "MODEL_UNAVAILABLE",
    "MODEL_TIMEOUT",
    "RATE_LIMITED",
    "INVALID_OUTPUT",
    "LLM_ERROR",
)


def get_session_store(request: Request) -> SessionStore:
    """FastAPI dependency: the session store that `create_app` attached to the app."""
    store = request.app.state.session_store
    if not isinstance(store, SessionStore):
        raise RuntimeError("the app has no session store; build it with create_app()")
    return store


def get_interview_service(
    store: Annotated[SessionStore, Depends(get_session_store)],
    llm: Annotated[LLMClient, Depends(llm_dep)],
    settings: Annotated[Settings, Depends(get_settings)],
    content: Annotated[ContentRegistry, Depends(get_registry)],
) -> InterviewService:
    """FastAPI dependency: the interview service for this request (it holds no state)."""
    return InterviewService(
        store=store,
        llm=llm,
        settings=settings,
        events=event_logger_for(settings.DATA_DIR),
        content=content,
    )


Service = Annotated[InterviewService, Depends(get_interview_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post(
    "",
    status_code=201,
    response_model=SessionCreatedDTO,
    responses=error_responses("UNKNOWN_CLIENT", "INVALID_INPUT", "INTERNAL_ERROR"),
)
async def create_session(
    body: CreateSessionDTO, service: Service, settings: SettingsDep
) -> SessionCreatedDTO:
    """Start an interview with a client. The opening line comes from the content."""
    session = await service.create_session(body.client_id, body.language)
    return session_created_dto(session, settings)


@router.get(
    "/{session_id}",
    response_model=SessionPublicDTO,
    responses=error_responses("SESSION_NOT_FOUND", "INVALID_INPUT", "INTERNAL_ERROR"),
)
async def get_session(session_id: str, service: Service, settings: SettingsDep) -> SessionPublicDTO:
    """The session's card, status, transcript and counters (for a page refresh)."""
    return session_public_dto(service.get_session(session_id), settings)


@router.post(
    "/{session_id}/messages",
    response_model=MessageResultDTO,
    responses=error_responses(
        "SESSION_NOT_FOUND",
        "SESSION_BUSY",
        "TURN_LIMIT",
        "INVALID_STATE",
        "INVALID_INPUT",
        "SESSION_RATE_LIMIT",
        *_MODEL_ERRORS,
        "INTERNAL_ERROR",
    ),
    dependencies=[Depends(throttle_messages)],
)
async def send_message(
    session_id: str, body: StudentMessageDTO, service: Service, settings: SettingsDep
) -> MessageResultDTO:
    """Send the student's message and get the client's reply.

    If a model fails, nothing is saved, so the same message can simply be sent again. A
    second message within `MIN_MESSAGE_INTERVAL_S` (1 s) gets `SESSION_RATE_LIMIT`.
    """
    result = await service.student_message(session_id, body.text)
    return message_result_dto(result, settings)


@router.post(
    "/{session_id}/wrapup",
    response_model=SessionPublicDTO,
    responses=error_responses(
        "SESSION_NOT_FOUND", "SESSION_BUSY", "INVALID_STATE", "INVALID_INPUT", "INTERNAL_ERROR"
    ),
)
async def wrap_up(
    session_id: str, body: WrapUpDTO, service: Service, settings: SettingsDep
) -> SessionPublicDTO:
    """End the interview with the student's summary and 1–3 product recommendations."""
    wrapup = WrapUp(
        needs_summary=body.needs_summary,
        recommendations=[
            Recommendation(product_id=item.product_id, reason=item.reason)
            for item in body.recommendations
        ],
    )
    return session_public_dto(await service.wrap_up(session_id, wrapup), settings)


@router.delete(
    "/{session_id}",
    status_code=204,
    response_class=Response,
    responses=error_responses(
        "SESSION_NOT_FOUND", "SESSION_BUSY", "INVALID_INPUT", "INTERNAL_ERROR"
    ),
)
async def delete_session(session_id: str, service: Service) -> Response:
    """Delete the session and its transcript."""
    await service.delete_session(session_id)
    return Response(status_code=204)
