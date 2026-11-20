"""Keep the content current while the app runs: reload changed files, keep the last good version."""

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request

from app.content.loader import BANK_FILE, CLIENTS_DIR, PRODUCTS_DIR, ContentValidationError
from app.content.registry import ContentRegistry, load_registry

logger = logging.getLogger(__name__)

CHECK_INTERVAL_S = 2.0
_now = time.monotonic  # module-level so tests can move the clock

Fingerprint = tuple[tuple[str, int, int], ...]


def fingerprint(content_dir: Path) -> Fingerprint:
    """Path, modification time and size of every file the loader reads.

    Comparing whole fingerprints, not just the latest time, also catches deleted files.
    """
    candidates = [content_dir / BANK_FILE]
    for folder in (PRODUCTS_DIR, CLIENTS_DIR):
        try:
            candidates.extend((content_dir / folder).iterdir())
        except OSError:  # a missing folder is the loader's error to report
            continue
    entries = []
    for path in candidates:
        try:
            stat = path.stat()
        except OSError:  # missing, or deleted while we looked
            continue
        relative = path.relative_to(content_dir).as_posix()
        entries.append((relative, stat.st_mtime_ns, stat.st_size))
    return tuple(sorted(entries))


@dataclass(frozen=True)
class ContentStatus:
    """`ok` is false while the files on disk are invalid and the last good version is served."""

    ok: bool
    errors: tuple[str, ...]


class ContentStore:
    """The current content of one folder, reloaded when its files change.

    Edits are noticed within `CHECK_INTERVAL_S`. If edited content is invalid, the store keeps
    serving the last good version, logs the errors and reports them in `status`.
    """

    def __init__(self, content_dir: Path) -> None:
        """Load the content now. Raises `ContentValidationError` if it's invalid: with no
        good version to fall back on, the app must not start."""
        self._dir = content_dir
        self._fingerprint = fingerprint(content_dir)
        self._registry = load_registry(content_dir)
        self._errors: tuple[str, ...] = ()
        self._checked_at = _now()
        self._lock = asyncio.Lock()

    @property
    def status(self) -> ContentStatus:
        return ContentStatus(ok=not self._errors, errors=self._errors)

    async def current(self) -> ContentRegistry:
        """The registry, reloaded first if a content file changed."""
        await self.refresh()
        return self._registry

    async def refresh(self) -> None:
        """Reload the content if any file changed, checking at most every 2 seconds."""
        if not self._due():
            return
        async with self._lock:
            if not self._due():  # another request checked while this one waited
                return
            self._checked_at = _now()
            latest = await asyncio.to_thread(fingerprint, self._dir)
            if latest == self._fingerprint:
                return
            try:
                registry = await asyncio.to_thread(load_registry, self._dir)
            except ContentValidationError as exc:
                self._fingerprint = latest
                self._errors = tuple(exc.messages)
                logger.warning(
                    "Content changed but is invalid; still serving the last good version",
                    extra={"content_errors": list(self._errors)},
                )
                return
            self._fingerprint = latest
            self._registry = registry
            self._errors = ()
            logger.info(
                "Content reloaded",
                extra={
                    "products": len(registry.list_products()),
                    "clients": len(registry.list_clients()),
                },
            )

    def _due(self) -> bool:
        return _now() - self._checked_at >= CHECK_INTERVAL_S


def get_content_store(request: Request) -> ContentStore:
    """FastAPI dependency: the content store that `create_app` attached to the app."""
    store = request.app.state.content_store
    if not isinstance(store, ContentStore):
        raise RuntimeError("the app has no content store; build it with create_app()")
    return store


async def get_registry(
    store: Annotated[ContentStore, Depends(get_content_store)],
) -> ContentRegistry:
    """FastAPI dependency: the current content, reloaded first if a file changed."""
    return await store.current()
