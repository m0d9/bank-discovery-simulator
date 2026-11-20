"""Load the prompt templates in this folder and fill in their `$placeholders`.

Every `*.md` file here is a `string.Template`. Templates are read once, at import, so a broken
template fails at startup rather than in the middle of an interview.
"""

import hashlib
from collections.abc import Mapping
from pathlib import Path
from string import Template
from types import MappingProxyType

PROMPTS_DIR = Path(__file__).resolve().parent
_VERSION_LENGTH = 8


def _version(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:_VERSION_LENGTH]


def _load() -> tuple[dict[str, Template], dict[str, str]]:
    templates: dict[str, Template] = {}
    versions: dict[str, str] = {}
    for path in sorted(PROMPTS_DIR.glob("*.md")):
        data = path.read_bytes()
        template = Template(data.decode("utf-8"))
        if not template.is_valid():
            raise ValueError(f"prompt template {path.name} has a `$` that isn't a placeholder")
        templates[path.stem] = template
        versions[path.stem] = _version(data)
    return templates, versions


_TEMPLATES, _VERSIONS = _load()

PROMPT_VERSION: Mapping[str, str] = MappingProxyType(_VERSIONS)
"""Template name (file name without `.md`) -> first 8 hex characters of its sha256."""


def render(template_name: str, /, **values: object) -> str:
    """Return the template with every placeholder replaced by `values`.

    The name is positional-only, so a placeholder may itself be called `name`. Raises KeyError
    for an unknown template or a missing value, and ValueError for a value the template doesn't
    use: a prompt with a hole or a typo in it must never reach a model.
    """
    try:
        template = _TEMPLATES[template_name]
    except KeyError:
        raise KeyError(f"no prompt template named {template_name!r}") from None
    unused = set(values) - set(template.get_identifiers())
    if unused:
        names = ", ".join(sorted(unused))
        raise ValueError(f"prompt {template_name!r} has no placeholder for: {names}")
    return template.substitute({key: str(value) for key, value in values.items()})
