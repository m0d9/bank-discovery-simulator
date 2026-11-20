"""An in-memory LRU cache of coach outcomes, shared by every request.

A request for a key whose coach call is still running waits for that same call instead of
starting another. A page refresh, or React running an effect twice in development, must not
cost a second coach call or end in `SESSION_BUSY`.
"""

import asyncio
from collections import OrderedDict
from collections.abc import Callable, Coroutine
from typing import Any

from app.coaching.coach import CoachOutcome

CACHE_SIZE = 128

CoachRun = Callable[[], Coroutine[Any, Any, CoachOutcome]]


class CoachCache:
    """Coach outcomes by key, least recently used first. Degraded outcomes are never kept, so
    trying again really asks the coach again."""

    def __init__(self, max_entries: int = CACHE_SIZE) -> None:
        self._max = max_entries
        self._entries: OrderedDict[str, CoachOutcome] = OrderedDict()
        self._running: dict[str, asyncio.Task[CoachOutcome]] = {}

    def __len__(self) -> int:
        return len(self._entries)

    async def get_or_run(self, key: str, run: CoachRun) -> tuple[CoachOutcome, bool]:
        """The outcome for `key`, and whether it was reused (cached, or already running)."""
        cached = self._entries.get(key)
        if cached is not None:
            self._entries.move_to_end(key)
            return cached, True
        task = self._running.get(key)
        reused = task is not None
        if task is None:
            task = asyncio.create_task(run())
            self._running[key] = task
            task.add_done_callback(lambda done: self._finish(key, done))
        # Shielded, so a request that goes away (a closed tab) doesn't cancel a call that
        # another request may be waiting for; its result is cached all the same.
        return await asyncio.shield(task), reused

    def _finish(self, key: str, task: asyncio.Task[CoachOutcome]) -> None:
        if self._running.get(key) is task:
            del self._running[key]
        if task.cancelled() or task.exception() is not None:
            return
        outcome = task.result()
        if outcome.degraded:
            return
        self._entries[key] = outcome
        self._entries.move_to_end(key)
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)
