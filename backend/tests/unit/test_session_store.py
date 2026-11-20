import asyncio
from datetime import datetime, timedelta

import pytest

from app.simulation.errors import SessionBusy, SessionNotFound
from app.simulation.store import SessionStore
from tests.interview_factory import T0, make_session


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, minutes: float) -> None:
        self.now += timedelta(minutes=minutes)


@pytest.fixture
def clock() -> Clock:
    return Clock()


def make_store(clock: Clock, *, ttl_minutes: int = 120, max_sessions: int = 200) -> SessionStore:
    return SessionStore(ttl_minutes=ttl_minutes, max_sessions=max_sessions, clock=clock)


def test_create_get_touch_and_delete(clock: Clock) -> None:
    store = make_store(clock)
    session = make_session("s1")
    store.create(session)

    assert store.get("s1") is session
    clock.advance(5)
    store.touch("s1")
    assert session.last_active_at == T0 + timedelta(minutes=5)

    store.delete("s1")
    with pytest.raises(SessionNotFound):
        store.get("s1")
    with pytest.raises(SessionNotFound):
        store.delete("s1")
    with pytest.raises(SessionNotFound):
        store.touch("s1")


async def test_a_busy_session_refuses_a_second_operation(clock: Clock) -> None:
    store = make_store(clock)
    store.create(make_session("s1"))
    store.create(make_session("s2"))

    async with store.locked("s1"):
        with pytest.raises(SessionBusy):
            async with store.locked("s1"):
                pass
        async with store.locked("s2"):  # other sessions are unaffected
            pass

    async with store.locked("s1"):  # free again once the first operation is done
        pass


async def test_an_unknown_session_cannot_be_locked(clock: Clock) -> None:
    with pytest.raises(SessionNotFound):
        async with make_store(clock).locked("missing"):
            pass


async def test_sessions_idle_past_the_ttl_expire_unless_busy(clock: Clock) -> None:
    store = make_store(clock, ttl_minutes=120)
    for session_id in ("idle", "active", "busy"):
        store.create(make_session(session_id))
    clock.advance(60)
    store.touch("active")
    clock.advance(61)  # idle and busy: 121 min idle; active: 61 min

    async with store.locked("busy"):
        assert store.remove_expired() == 1

    with pytest.raises(SessionNotFound):
        store.get("idle")
    assert store.get("active") and store.get("busy")
    assert store.remove_expired() == 1  # busy, no longer locked


def test_a_full_store_evicts_the_least_recently_used_session(clock: Clock) -> None:
    store = make_store(clock, max_sessions=2)
    store.create(make_session("s1"))
    store.create(make_session("s2"))
    store.touch("s1")  # s2 is now the least recently used

    store.create(make_session("s3"))

    assert len(store) == 2
    with pytest.raises(SessionNotFound):
        store.get("s2")
    assert store.get("s1") and store.get("s3")


async def test_eviction_skips_a_session_whose_turn_is_in_progress(clock: Clock) -> None:
    store = make_store(clock, max_sessions=2)
    store.create(make_session("s1"))
    store.create(make_session("s2"))

    async with store.locked("s1"):  # s1 is the least recently used, but busy
        store.create(make_session("s3"))

    assert store.get("s1") and store.get("s3")
    with pytest.raises(SessionNotFound):
        store.get("s2")


async def test_the_cleanup_task_removes_expired_sessions_until_stopped(clock: Clock) -> None:
    store = make_store(clock, ttl_minutes=1)
    store.create(make_session("s1"))
    clock.advance(2)

    store.start_cleanup(interval_s=0.01)
    for _ in range(100):
        if not len(store):
            break
        await asyncio.sleep(0.01)
    await store.stop_cleanup()

    assert len(store) == 0
    await store.stop_cleanup()  # stopping twice is harmless
