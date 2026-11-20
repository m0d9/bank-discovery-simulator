import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from app.content import ContentRegistry, ContentStatus, ContentStore, ContentValidationError
from app.content import store as store_module
from tests.content_factory import CLIENT, SECRET_CASH_GAP, ContentDir, client_data

BROKEN = "content/clients/test-client.yaml › difficulty: Input should be 'easy', 'medium' or 'hard'"


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    now = [1000.0]
    monkeypatch.setattr(store_module, "_now", lambda: now[0])
    return now


@pytest.fixture
def loads(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Folders the store re-validated, in order (the real loader still runs)."""
    calls: list[Path] = []
    real: Callable[[Path], ContentRegistry] = store_module.load_registry

    def counting(content_dir: Path) -> ContentRegistry:
        calls.append(content_dir)
        return real(content_dir)

    monkeypatch.setattr(store_module, "load_registry", counting)
    return calls


def headline(registry: ContentRegistry) -> str:
    return registry.get_client(CLIENT).card.headline.en


def with_headline(text: str) -> dict[str, object]:
    data = client_data()
    data["card"]["headline"] = text
    return data


async def test_serves_the_content_it_loaded(content: ContentDir, clock: list[float]) -> None:
    store = ContentStore(content.root)

    assert headline(await store.current()) == "Owns a small test company"
    assert store.status == ContentStatus(ok=True, errors=())


async def test_a_changed_file_shows_up_after_at_most_two_seconds(
    content: ContentDir, clock: list[float]
) -> None:
    store = ContentStore(content.root)
    content.write(f"clients/{CLIENT}.yaml", with_headline("Now runs two companies"))

    clock[0] += 1.9
    assert headline(await store.current()) == "Owns a small test company"
    clock[0] += 0.1
    assert headline(await store.current()) == "Now runs two companies"


async def test_unchanged_files_are_not_validated_again(
    content: ContentDir, clock: list[float], loads: list[Path]
) -> None:
    store = ContentStore(content.root)
    loads.clear()  # count reloads only, not the initial load
    for _ in range(3):
        clock[0] += 5
        await store.current()
    assert loads == []


async def test_invalid_edits_keep_the_last_good_version_and_are_reported(
    content: ContentDir,
    clock: list[float],
    loads: list[Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = ContentStore(content.root)
    loads.clear()  # count reloads only, not the initial load
    content.write(f"clients/{CLIENT}.yaml", client_data(difficulty="expert"))
    clock[0] += 2

    with caplog.at_level(logging.WARNING, logger="app.content.store"):
        registry = await store.current()

    assert registry.get_client(CLIENT).difficulty == "easy"  # the last good version
    assert store.status == ContentStatus(ok=False, errors=(BROKEN,))
    [record] = [r for r in caplog.records if r.name == "app.content.store"]
    assert getattr(record, "content_errors", None) == [BROKEN]
    assert SECRET_CASH_GAP not in caplog.text

    clock[0] += 2
    await store.current()
    assert len(loads) == 1  # the same broken files aren't validated again

    content.write(f"clients/{CLIENT}.yaml", client_data(difficulty="hard"))
    clock[0] += 2
    assert (await store.current()).get_client(CLIENT).difficulty == "hard"
    assert store.status == ContentStatus(ok=True, errors=())


async def test_added_and_deleted_files_are_noticed(content: ContentDir, clock: list[float]) -> None:
    store = ContentStore(content.root)

    content.write("clients/second.yaml", client_data("second"))
    clock[0] += 2
    assert {client.id for client in (await store.current()).list_clients()} == {CLIENT, "second"}

    content.remove("clients/second.yaml")
    clock[0] += 2
    assert {client.id for client in (await store.current()).list_clients()} == {CLIENT}


def test_invalid_content_at_startup_fails_fast(content: ContentDir) -> None:
    content.write(f"clients/{CLIENT}.yaml", client_data(difficulty="expert"))
    with pytest.raises(ContentValidationError) as caught:
        ContentStore(content.root)
    assert caught.value.messages == [BROKEN]
