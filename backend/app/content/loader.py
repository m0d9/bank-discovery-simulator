"""Read every content file and validate it on its own, collecting all problems before failing.

An error names the file and the field, and never quotes the content. A YAML snippet or a
rejected value could contain a hidden fact, and these messages reach the logs and /api/health.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from app.content.models import Bank, Client, Product

BANK_FILE = "bank.yaml"
PRODUCTS_DIR = "products"
CLIENTS_DIR = "clients"
YAML_SUFFIX = ".yaml"


@dataclass(frozen=True)
class ContentIssue:
    """One problem in one file, printed as `content/x.yaml › field[0].name: message`."""

    path: str
    where: str
    message: str

    def __str__(self) -> str:
        if self.where:
            return f"{self.path} › {self.where}: {self.message}"
        return f"{self.path}: {self.message}"


class ContentValidationError(Exception):
    """The content is invalid. `messages` holds every problem, one line each."""

    def __init__(self, issues: Sequence[ContentIssue]) -> None:
        self.issues = tuple(issues)
        self.messages = [str(issue) for issue in self.issues]
        count = len(self.messages)
        heading = f"{count} content error{'' if count == 1 else 's'}:"
        super().__init__("\n".join([heading, *self.messages]))


@dataclass
class ParsedContent:
    """Each file that validated on its own, plus every problem found so far."""

    bank: Bank | None = None
    products: list[tuple[str, Product]] = field(default_factory=list)
    clients: list[tuple[str, Client]] = field(default_factory=list)
    # Ids of every product file present, valid or not, so one broken product doesn't also
    # produce "unknown product" errors in every client that mentions it.
    product_files: frozenset[str] = frozenset()
    issues: list[ContentIssue] = field(default_factory=list)


class _StrictLoader(yaml.SafeLoader):
    """A SafeLoader that rejects duplicate keys, which PyYAML would silently overwrite."""


def _mapping_without_duplicates(loader: yaml.SafeLoader, node: yaml.Node) -> dict[Any, Any]:
    if not isinstance(node, yaml.MappingNode):  # only registered for mappings
        raise TypeError(f"expected a mapping node, got {type(node).__name__}")
    seen: set[Any] = set()
    for key_node, _ in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            continue
        key = loader.construct_object(key_node, deep=True)
        try:
            duplicate = key in seen
        except TypeError:  # an unhashable key: construct_mapping reports it properly
            continue
        if duplicate:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate key '{key}'", key_node.start_mark
            )
        seen.add(key)
    return loader.construct_mapping(node, deep=True)


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping_without_duplicates
)


def format_location(loc: Sequence[int | str]) -> str:
    """Turn a Pydantic error location into `hidden_facts[1].unlock_when`."""
    text = ""
    for part in loc:
        if isinstance(part, int):
            text += f"[{part}]"
        else:
            text += f".{part}" if text else part
    return text


def parse_content(content_dir: Path) -> ParsedContent:
    """Read `bank.yaml`, `products/*.yaml` and `clients/*.yaml`, validating each file alone.

    Files whose names start with `_` (templates) or `.` are ignored. Checks across files
    happen in the registry.
    """
    parsed = ParsedContent()
    if not content_dir.is_dir():
        parsed.issues.append(
            ContentIssue(content_dir.name or str(content_dir), "", "folder not found")
        )
        return parsed

    reader = _Reader(content_dir, parsed.issues)
    bank_path = content_dir / BANK_FILE
    if bank_path.is_file():
        parsed.bank = reader.read(bank_path, Bank)
    else:
        parsed.issues.append(ContentIssue(reader.shown(bank_path), "", "file not found"))

    product_paths = reader.yaml_files(content_dir / PRODUCTS_DIR)
    parsed.product_files = frozenset(path.stem for path in product_paths)
    for path in product_paths:
        product = reader.read(path, Product, id_from_name=True)
        if product is not None:
            parsed.products.append((reader.shown(path), product))
    for path in reader.yaml_files(content_dir / CLIENTS_DIR):
        client = reader.read(path, Client, id_from_name=True)
        if client is not None:
            parsed.clients.append((reader.shown(path), client))
    return parsed


class _Reader:
    """Reads files under one content folder, recording problems instead of raising."""

    def __init__(self, content_dir: Path, issues: list[ContentIssue]) -> None:
        self._dir = content_dir
        self._issues = issues

    def shown(self, path: Path) -> str:
        """How a file is named in messages: `content/clients/x.yaml`."""
        return f"{self._dir.name}/{path.relative_to(self._dir).as_posix()}"

    def yaml_files(self, directory: Path) -> list[Path]:
        if not directory.is_dir():
            self._issues.append(ContentIssue(self.shown(directory), "", "folder not found"))
            return []
        found = []
        for path in sorted(directory.iterdir()):
            if path.name.startswith(("_", ".")) or not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix == ".yml":
                self._issue(path, "", "rename it to .yaml: only .yaml files are loaded")
            elif suffix == YAML_SUFFIX:
                found.append(path)
        return found

    def read[M: BaseModel](
        self, path: Path, model: type[M], *, id_from_name: bool = False
    ) -> M | None:
        data = self._load_yaml(path)
        if data is None:
            return None
        if id_from_name and "id" in data and data["id"] != path.stem:
            self._issue(path, "id", f"must match the file name: '{path.stem}'")
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            # include_input=False: the rejected value itself could be private text.
            for error in exc.errors(include_url=False, include_context=False, include_input=False):
                self._issue(path, format_location(error["loc"]), error["msg"])
            return None

    def _load_yaml(self, path: Path) -> dict[str, Any] | None:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            self._issue(path, "", "is not valid UTF-8 text")
            return None
        except OSError as exc:
            self._issue(path, "", f"can't be read ({exc.strerror or type(exc).__name__})")
            return None
        try:
            data = yaml.load(text, Loader=_StrictLoader)
        except yaml.MarkedYAMLError as exc:
            # Never str(exc): it quotes the offending line, which may be a hidden fact.
            mark = exc.problem_mark or exc.context_mark
            where = f"line {mark.line + 1}, column {mark.column + 1}" if mark else ""
            self._issue(path, where, exc.problem or exc.context or "invalid YAML")
            return None
        except yaml.YAMLError:
            self._issue(path, "", "is not valid YAML")
            return None
        if data is None:
            self._issue(path, "", "is empty")
            return None
        if not isinstance(data, dict):
            self._issue(path, "", "should be a mapping of fields (`key: value` lines)")
            return None
        return data

    def _issue(self, path: Path, where: str, message: str) -> None:
        self._issues.append(ContentIssue(self.shown(path), where, message))
