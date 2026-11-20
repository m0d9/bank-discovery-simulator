"""Validated content in memory, and the checks that span facts, needs and files."""

from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

from app.content.loader import ContentIssue, ContentValidationError, ParsedContent, parse_content
from app.content.models import Bank, Client, HiddenFact, Product

_DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}


class UnknownClient(LookupError):
    """No client has this id."""

    def __init__(self, client_id: str) -> None:
        super().__init__(client_id)
        self.client_id = client_id


class UnknownProduct(LookupError):
    """No product has this id."""

    def __init__(self, product_id: str) -> None:
        super().__init__(product_id)
        self.product_id = product_id


class ContentRegistry:
    """Read-only, fully validated content. Build it with `load_registry()`."""

    def __init__(self, bank: Bank, products: Iterable[Product], clients: Iterable[Client]) -> None:
        self._bank = bank
        self._products = {product.id: product for product in sorted(products, key=_product_key)}
        self._clients = {client.id: client for client in sorted(clients, key=_client_key)}

    @property
    def bank(self) -> Bank:
        return self._bank

    def get_client(self, client_id: str) -> Client:
        """Return the client with this id, or raise `UnknownClient`."""
        try:
            return self._clients[client_id]
        except KeyError:
            raise UnknownClient(client_id) from None

    def list_clients(self) -> list[Client]:
        """Every client, easiest first, then by id."""
        return list(self._clients.values())

    def get_product(self, product_id: str) -> Product:
        """Return the product with this id, or raise `UnknownProduct`."""
        try:
            return self._products[product_id]
        except KeyError:
            raise UnknownProduct(product_id) from None

    def list_products(self) -> list[Product]:
        """Every product, by id."""
        return list(self._products.values())


def _product_key(product: Product) -> str:
    return product.id


def _client_key(client: Client) -> tuple[int, str]:
    return _DIFFICULTY_ORDER[client.difficulty], client.id


def load_registry(content_dir: Path) -> ContentRegistry:
    """Load and fully validate a content folder.

    Raises `ContentValidationError` listing every problem in every file, grouped by file.
    """
    parsed = parse_content(content_dir)
    issues = [*parsed.issues, *cross_check(parsed)]
    if issues or parsed.bank is None:
        # A stable sort groups problems by file and keeps each file's own order.
        raise ContentValidationError(sorted(issues, key=lambda issue: issue.path))
    return ContentRegistry(
        parsed.bank,
        (product for _, product in parsed.products),
        (client for _, client in parsed.clients),
    )


def cross_check(parsed: ParsedContent) -> list[ContentIssue]:
    """Checks that need more than one field: ids, references, cycles and the answer key."""
    issues = _duplicate_model_ids(parsed.products) + _duplicate_model_ids(parsed.clients)
    for shown, client in parsed.clients:
        issues += [
            ContentIssue(shown, where, message)
            for where, message in _client_problems(client, parsed.product_files)
        ]
    return issues


def _duplicate_model_ids(models: Sequence[tuple[str, Product | Client]]) -> list[ContentIssue]:
    first_path: dict[str, str] = {}
    issues = []
    for shown, model in models:
        if model.id in first_path:
            issues.append(
                ContentIssue(shown, "id", f"'{model.id}' is also used by {first_path[model.id]}")
            )
        else:
            first_path[model.id] = shown
    return issues


def _client_problems(client: Client, products: frozenset[str]) -> Iterator[tuple[str, str]]:
    """Yield (field, message) for every cross-field problem in one client."""
    fact_ids = {fact.id for fact in client.hidden_facts}
    yield from _duplicates("hidden_facts", [fact.id for fact in client.hidden_facts])
    yield from _duplicates("needs", [need.id for need in client.needs])

    for i, fact in enumerate(client.hidden_facts):
        for j, product_id in enumerate(fact.unlock_on_product_pitch):
            if product_id not in products:
                yield (
                    f"hidden_facts[{i}].unlock_on_product_pitch[{j}]",
                    f"unknown product '{product_id}'",
                )
        for j, fact_id in enumerate(fact.requires):
            if fact_id not in fact_ids:
                yield f"hidden_facts[{i}].requires[{j}]", f"unknown hidden fact '{fact_id}'"
    for index, cycle in _requires_cycles(client.hidden_facts):
        yield f"hidden_facts[{index}].requires", "circular requirement: " + " → ".join(cycle)

    for i, need in enumerate(client.needs):
        for j, fact_id in enumerate(need.evidence_facts):
            if fact_id not in fact_ids:
                yield f"needs[{i}].evidence_facts[{j}]", f"unknown hidden fact '{fact_id}'"
        for j, product_id in enumerate(need.suitable_products):
            if product_id not in products:
                yield f"needs[{i}].suitable_products[{j}]", f"unknown product '{product_id}'"
        unsuitable = [entry.id for entry in need.unsuitable_products]
        yield from _duplicates(f"needs[{i}].unsuitable_products", unsuitable)
        for j, product_id in enumerate(unsuitable):
            where = f"needs[{i}].unsuitable_products[{j}].id"
            if product_id not in products:
                yield where, f"unknown product '{product_id}'"
            elif product_id in need.suitable_products:
                yield where, f"'{product_id}' is also listed in suitable_products for this need"
        if not need.suitable_products and not client.no_catalogue_fit:
            yield (
                f"needs[{i}].suitable_products",
                "list at least one product, or set no_catalogue_fit: true and add a referral_note",
            )

    if not any(fact.importance == "critical" for fact in client.hidden_facts):
        yield "hidden_facts", "at least one hidden fact must have importance: critical"


def _duplicates(where: str, ids: Sequence[str]) -> Iterator[tuple[str, str]]:
    seen: set[str] = set()
    for index, value in enumerate(ids):
        if value in seen:
            yield f"{where}[{index}].id", f"duplicate id '{value}'"
        seen.add(value)


def _requires_cycles(facts: Sequence[HiddenFact]) -> list[tuple[int, list[str]]]:
    """Each cycle in `requires`, once, as (index of the fact it starts at, [a, b, a])."""
    index = {fact.id: i for i, fact in enumerate(facts)}
    graph = {fact.id: [req for req in fact.requires if req in index] for fact in facts}
    state: dict[str, str] = {}  # "visiting" while on the current path, then "done"
    path: list[str] = []
    cycles: list[tuple[int, list[str]]] = []
    seen: set[frozenset[str]] = set()

    def visit(fact_id: str) -> None:
        state[fact_id] = "visiting"
        path.append(fact_id)
        for required in graph[fact_id]:
            if state.get(required) == "visiting":
                cycle = [*path[path.index(required) :], required]
                if frozenset(cycle) not in seen:
                    seen.add(frozenset(cycle))
                    cycles.append((index[required], cycle))
            elif required not in state:
                visit(required)
        path.pop()
        state[fact_id] = "done"

    for fact in facts:
        if fact.id not in state:
            visit(fact.id)
    return cycles
