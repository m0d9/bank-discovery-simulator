"""Reusable check that a public response carries no private content (CLAUDE.md rule 3).

Use it on every response a student can see before the session reaches `feedback_ready`:

    assert_no_leak(response.json(), registry)

It fails on any of `PRIVATE_KEYS` used as a JSON key anywhere in the payload, and on any
hidden fact's content appearing in any key or string (or in the serialised text).
"""

import json
from collections.abc import Collection
from typing import Any

from app.content import ContentRegistry

PRIVATE_KEYS = frozenset(
    {
        "persona",
        "hidden_facts",
        "needs",
        "coach_notes",
        "unlock_when",
        "signal",
        "example_questions",
        "referral_note",
        "content",
    }
)


def find_leaks(
    payload: Any, registry: ContentRegistry, *, allowed_keys: Collection[str] = ()
) -> list[str]:
    """Describe every leak in a decoded JSON payload (empty when it's clean).

    `allowed_keys` lists exact paths, such as `$.content`, that may use a private key's name
    for something else. What's inside them is still checked.
    """
    secrets = [fact.content for client in registry.list_clients() for fact in client.hidden_facts]
    leaks: list[str] = []

    def check_text(text: str, path: str) -> None:
        for secret in secrets:
            if secret in text:
                leaks.append(f"{path}: contains a hidden fact ({secret[:30]}...)")

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                child = f"{path}.{key}"
                if key in PRIVATE_KEYS and child not in allowed_keys:
                    leaks.append(f"{child}: private key '{key}'")
                check_text(str(key), child)
                walk(item, child)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
        elif isinstance(value, str):
            check_text(value, path)

    walk(payload, "$")
    if not leaks:
        # The text as the browser receives it, in case a secret only appears once serialised.
        check_text(json.dumps(payload, ensure_ascii=False), "$ (serialised)")
    return leaks


def assert_no_leak(
    payload: Any, registry: ContentRegistry, *, allowed_keys: Collection[str] = ()
) -> None:
    """Fail with a list of every leak found in `payload`."""
    leaks = find_leaks(payload, registry, allowed_keys=allowed_keys)
    assert not leaks, "private content in a public response:\n" + "\n".join(leaks)
