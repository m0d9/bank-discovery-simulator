"""In-memory interview sessions: lookup, one lock per session, expiry and eviction."""

import asyncio
import contextlib
import logging
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.simulation.errors import SessionBusy, SessionNotFound
from app.simulation.models import Session

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_S = 300.0


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class _Entry:
    session: Session
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SessionStore:
    """Sessions by id, least recently used first.

    A turn holds its session's lock while the models answer, and a second request for the
    same session gets `SessionBusy` instead of waiting. Idle sessions expire after the TTL, and
    when the store is full the least recently used session makes room. Neither ever removes a
    session whose lock is held.
    """

    def __init__(
        self,
        *,
        ttl_minutes: int,
        max_sessions: int,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._ttl = timedelta(minutes=ttl_minutes)
        self._max = max_sessions
        self._clock = clock
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._cleanup: asyncio.Task[None] | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "SessionStore":
        """A store with the TTL and size limit from settings."""
        return cls(ttl_minutes=settings.SESSION_TTL_MINUTES, max_sessions=settings.MAX_SESSIONS)

    def __len__(self) -> int:
        return len(self._entries)

    def now(self) -> datetime:
        """The store's clock (UTC). Sessions take their timestamps from it too."""
        return self._clock()

    def create(self, session: Session) -> None:
        """Add a new session, first evicting the least recently used one if the store is full."""
        while len(self._entries) >= self._max and self._evict_least_recently_used():
            pass
        self._entries[session.id] = _Entry(session)

    def get(self, session_id: str) -> Session:
        """Return the session, or raise `SessionNotFound`."""
        return self._entry(session_id).session

    def touch(self, session_id: str) -> None:
        """Mark the session as just used, which also moves it to the back of the eviction order."""
        self._entry(session_id).session.last_active_at = self.now()
        self._entries.move_to_end(session_id)

    def delete(self, session_id: str) -> None:
        """Remove the session, or raise `SessionNotFound`."""
        self._entry(session_id)
        del self._entries[session_id]

    @asynccontextmanager
    async def locked(self, session_id: str) -> AsyncIterator[Session]:
        """Hold the session's lock for one operation; raise `SessionBusy` if it's already held."""
        entry = self._entry(session_id)
        # Check-then-acquire is safe: nothing else runs between the two on one event loop.
        if entry.lock.locked():
            raise SessionBusy("another request is still working on this session")
        async with entry.lock:
            yield entry.session

    def remove_expired(self) -> int:
        """Remove sessions idle for longer than the TTL, except busy ones. Returns the count."""
        cutoff = self.now() - self._ttl
        expired = [
            session_id
            for session_id, entry in self._entries.items()
            if not entry.lock.locked() and entry.session.last_active_at < cutoff
        ]
        for session_id in expired:
            del self._entries[session_id]
        return len(expired)

    def start_cleanup(self, interval_s: float = CLEANUP_INTERVAL_S) -> None:
        """Remove expired sessions every `interval_s` seconds. Call it inside the event loop."""
        if self._cleanup is None:
            self._cleanup = asyncio.create_task(self._cleanup_loop(interval_s))

    async def stop_cleanup(self) -> None:
        """Stop the cleanup task, if it's running."""
        task, self._cleanup = self._cleanup, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _cleanup_loop(self, interval_s: float) -> None:
        while True:
            await asyncio.sleep(interval_s)
            removed = self.remove_expired()
            if removed:
                logger.info(
                    "Expired sessions removed", extra={"removed": removed, "sessions": len(self)}
                )

    def _evict_least_recently_used(self) -> bool:
        idle = next((sid for sid, entry in self._entries.items() if not entry.lock.locked()), None)
        if idle is None:
            return False  # every session is mid-turn: go over the limit rather than refuse
        del self._entries[idle]
        logger.info("Least recently used session evicted", extra={"max_sessions": self._max})
        return True

    def _entry(self, session_id: str) -> _Entry:
        try:
            return self._entries[session_id]
        except KeyError:
            raise SessionNotFound("no session has this id; it may have expired") from None
