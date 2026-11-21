"""Per-session message throttle: a message that comes too soon after the last one in the same
session gets 429 `SESSION_RATE_LIMIT`.

It guards the HTTP route only. `scripts/` and `evals/` call `InterviewService` directly.
"""

import time

from fastapi import Request

from app.simulation import InterviewError

_now = time.monotonic  # module-level so tests can move the clock


class SessionRateLimited(InterviewError):
    """A message came too soon after the last one in the same session."""

    code = "SESSION_RATE_LIMIT"


class MessageThrottle:
    """At most one message per session every `min_interval_s` seconds (0 turns it off).

    The interval runs from each message's arrival, so a slow reply never delays the next
    question; a refused message doesn't restart it.
    """

    def __init__(self, min_interval_s: float) -> None:
        self._interval = min_interval_s
        self._last: dict[str, float] = {}

    def check(self, session_id: str) -> None:
        """Record a message for `session_id`, or raise `SessionRateLimited` if it's too soon."""
        if self._interval <= 0:
            return
        now = _now()
        # An older arrival can't limit anything, so only the last interval's sessions stay.
        self._last = {sid: at for sid, at in self._last.items() if now - at < self._interval}
        if session_id in self._last:
            raise SessionRateLimited(f"send at most one message every {self._interval:g} s")
        self._last[session_id] = now


def throttle_messages(session_id: str, request: Request) -> None:
    """FastAPI dependency: refuse a message that comes too soon after the session's last one."""
    throttle = request.app.state.message_throttle
    if not isinstance(throttle, MessageThrottle):
        raise RuntimeError("the app has no message throttle; build it with create_app()")
    throttle.check(session_id)
