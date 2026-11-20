"""Typed interview errors. `code` is also the API error code (`errors.<CODE>`)."""

from typing import ClassVar


class InterviewError(Exception):
    """Base class for interview failures. `detail` never contains message text."""

    code: ClassVar[str] = "INVALID_STATE"

    def __init__(self, detail: str = "") -> None:
        super().__init__(detail or self.code)
        self.detail = detail


class SessionNotFound(InterviewError):
    """No session has this id: it never existed, expired or was deleted."""

    code = "SESSION_NOT_FOUND"


class SessionBusy(InterviewError):
    """Another request is still working on this session."""

    code = "SESSION_BUSY"


class TurnLimitReached(InterviewError):
    """The student has used all of their messages."""

    code = "TURN_LIMIT"


class InvalidState(InterviewError):
    """The session isn't in a state that allows this, such as a message after wrap-up."""

    code = "INVALID_STATE"


class InvalidInput(InterviewError):
    """The request's content is unusable, such as an empty or over-long message."""

    code = "INVALID_INPUT"
