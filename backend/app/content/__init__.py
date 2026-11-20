"""Content: the bank, products and clients that faculty edit as YAML under `content/`.

Import from here. `load_registry()` validates a content folder once, for the CLI, scripts and
evaluations. The API reads content through the `get_registry` dependency, whose
`ContentStore` also reloads files that change while the app runs.
"""

from app.content.loader import ContentIssue, ContentValidationError
from app.content.models import (
    Bank,
    Card,
    Category,
    Client,
    CoachNotes,
    Difficulty,
    HiddenFact,
    Importance,
    LocalizedText,
    Need,
    Persona,
    Product,
    Segment,
    UnsuitableProduct,
)
from app.content.registry import ContentRegistry, UnknownClient, UnknownProduct, load_registry
from app.content.store import ContentStatus, ContentStore, get_content_store, get_registry

__all__ = [
    "Bank",
    "Card",
    "Category",
    "Client",
    "CoachNotes",
    "ContentIssue",
    "ContentRegistry",
    "ContentStatus",
    "ContentStore",
    "ContentValidationError",
    "Difficulty",
    "HiddenFact",
    "Importance",
    "LocalizedText",
    "Need",
    "Persona",
    "Product",
    "Segment",
    "UnknownClient",
    "UnknownProduct",
    "UnsuitableProduct",
    "get_content_store",
    "get_registry",
    "load_registry",
]
