import hashlib
import re

import pytest

from app.prompts import PROMPT_VERSION, render
from app.prompts.loader import PROMPTS_DIR

TEMPLATES = {"gate", "client_system", "client_reminder"}


def test_every_template_is_loaded_with_an_eight_character_version() -> None:
    assert set(PROMPT_VERSION) == TEMPLATES
    for name, version in PROMPT_VERSION.items():
        assert re.fullmatch(r"[0-9a-f]{8}", version), name


def test_the_version_is_the_start_of_the_template_files_sha256() -> None:
    for name, version in PROMPT_VERSION.items():
        data = (PROMPTS_DIR / f"{name}.md").read_bytes()
        assert version == hashlib.sha256(data).hexdigest()[:8]


def test_render_fills_in_every_placeholder() -> None:
    text = render("client_reminder", name="Noura Al-Kuwari", bank="Al Murjan Bank")

    assert "Noura Al-Kuwari" in text and "Al Murjan Bank" in text
    assert "$" not in text


def test_render_refuses_a_missing_value() -> None:
    with pytest.raises(KeyError, match="bank"):
        render("client_reminder", name="Noura Al-Kuwari")


def test_render_refuses_a_value_the_template_does_not_use() -> None:
    with pytest.raises(ValueError, match="nmae"):
        render("client_reminder", name="Noura", bank="Al Murjan Bank", nmae="typo")


def test_render_refuses_an_unknown_template() -> None:
    with pytest.raises(KeyError, match="no prompt template named 'nope'"):
        render("nope")
