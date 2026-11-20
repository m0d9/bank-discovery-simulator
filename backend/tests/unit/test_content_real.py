"""The repository's real `content/` folder: valid, bilingual where students read it, and in sync."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from app.content import Client, ContentRegistry, LocalizedText, load_registry
from app.content.__main__ import render_schemas, validate

REPO_CONTENT = Path(__file__).resolve().parents[3] / "content"
PRODUCT_IDS = [
    "business-collect-account",
    "business-overdraft",
    "ijara-asset-finance",
    "invoice-advance",
    "multicurrency-remit-account",
    "murabaha-working-capital",
    "salary-personal-finance",
    "wakala-term-deposit",
]
CLIENT_IDS = [  # easy, then medium, then hard; by id within each
    "fatima-al-sulaiti",
    "rajesh-menon",
    "ahmed-hassan",
    "noura-al-kuwari",
    "khalid-al-marri",
]
ARABIC_FICTIONAL_MARKER = "(أرقام افتراضية)"
ARABIC_INTEREST = "فائدة"
# Covers فائدة, الفائدة, فوائد and their other forms.
ARABIC_INTEREST_STEM = "فائد"
ARABIC_PROFIT = "ربح"


@pytest.fixture(scope="module")
def registry() -> ContentRegistry:
    return load_registry(REPO_CONTENT)


def test_the_real_content_validates(capsys: pytest.CaptureFixture[str]) -> None:
    assert validate(REPO_CONTENT) == 0
    assert capsys.readouterr().out == "✓ 8 products, 5 clients\n"


def test_the_catalogue_and_clients_are_the_ones_the_brief_fixes(registry: ContentRegistry) -> None:
    assert [product.id for product in registry.list_products()] == PRODUCT_IDS
    assert [client.id for client in registry.list_clients()] == CLIENT_IDS
    assert registry.bank.name.en == "Al Murjan Bank"
    assert registry.bank.currency == "QAR"


def test_the_templates_validate_when_copied_next_to_the_real_catalogue(tmp_path: Path) -> None:
    """A lecturer copies a template into `clients/` or `products/`: it must validate as it is."""
    content = tmp_path / "content"
    shutil.copytree(REPO_CONTENT / "products", content / "products")
    (content / "clients").mkdir()
    shutil.copy(REPO_CONTENT / "bank.yaml", content / "bank.yaml")
    copied: dict[str, str] = {}
    for kind, folder in (("client", "clients"), ("product", "products")):
        template = REPO_CONTENT / "_templates" / f"{kind}.yaml"
        # The template's own instructions: save it as <id>.yaml.
        copied[kind] = yaml.safe_load(template.read_text(encoding="utf-8"))["id"]
        shutil.copy(template, content / folder / f"{copied[kind]}.yaml")

    registry = load_registry(content)

    assert [client.id for client in registry.list_clients()] == [copied["client"]]
    assert copied["product"] in [product.id for product in registry.list_products()]
    assert len(registry.list_products()) == len(PRODUCT_IDS) + 1


def student_facing_text(registry: ContentRegistry) -> Iterator[tuple[str, LocalizedText]]:
    """Every field students read, as (where, text): the bank, client cards, the answer key's
    texts in the feedback, and products."""
    for field in ("name", "tagline", "disclaimer"):
        yield f"bank.{field}", getattr(registry.bank, field)
    for client in registry.list_clients():
        for field in ("name", "headline", "opening_line"):
            yield f"{client.id}.card.{field}", getattr(client.card, field)
        yield from answer_key_text(client)
    for product in registry.list_products():
        yield from product_text(product.id, registry)


def answer_key_text(client: Client) -> Iterator[tuple[str, LocalizedText]]:
    """What the feedback shows from the answer key: need descriptions, the reasons products
    are unsuitable, and the referral note."""
    for need in client.needs:
        yield f"{client.id}.needs.{need.id}.description", need.description
        for entry in need.unsuitable_products:
            yield f"{client.id}.needs.{need.id}.unsuitable.{entry.id}", entry.reason
    if client.referral_note is not None:
        yield f"{client.id}.referral_note", client.referral_note


def product_text(product_id: str, registry: ContentRegistry) -> Iterator[tuple[str, LocalizedText]]:
    product = registry.get_product(product_id)
    yield f"{product_id}.name", product.name
    yield f"{product_id}.summary", product.summary
    for field, items in [
        ("features", product.features),
        ("limitations", product.limitations),
        ("eligibility", product.eligibility),
    ]:
        for index, text in enumerate(items):
            yield f"{product_id}.{field}[{index}]", text
    yield f"{product_id}.pricing", product.pricing


def test_every_student_facing_field_has_arabic(registry: ContentRegistry) -> None:
    missing = [where for where, text in student_facing_text(registry) if not text.ar]
    assert missing == []


def test_pricing_is_marked_fictional_in_both_languages(registry: ContentRegistry) -> None:
    for product in registry.list_products():
        assert "(fictional)" in product.pricing.en, product.id
        assert product.pricing.ar and ARABIC_FICTIONAL_MARKER in product.pricing.ar, product.id


def test_arabic_keeps_islamic_and_conventional_terms_apart(registry: ContentRegistry) -> None:
    """Sharia-compliant products never say فائدة; interest-based ones say فائدة, never ربح."""
    for product in registry.list_products():
        arabic = " ".join(text.ar or "" for _, text in product_text(product.id, registry))
        if product.sharia_compliant:
            assert ARABIC_INTEREST_STEM not in arabic, product.id
        if product.interest_based:
            assert ARABIC_INTEREST in arabic, product.id
            assert ARABIC_PROFIT not in arabic, product.id


def content_files() -> list[Path]:
    files = [REPO_CONTENT / "bank.yaml"]
    for folder in ("products", "clients"):
        files += sorted((REPO_CONTENT / folder).glob("[!_]*.yaml"))
    return files


@pytest.mark.parametrize("path", content_files(), ids=lambda path: path.name)
def test_every_content_file_starts_with_its_schema_comment(path: Path) -> None:
    kind = {"products": "product", "clients": "client"}.get(path.parent.name, "bank")
    # bank.yaml sits beside schema/, the others one folder below it.
    folder = "./schema" if kind == "bank" else "../schema"
    first_line = path.read_text(encoding="utf-8").splitlines()[0]
    assert first_line == f"# yaml-language-server: $schema={folder}/{kind}.schema.json"


def test_the_committed_json_schemas_are_up_to_date() -> None:
    for name, text in render_schemas().items():
        committed = (REPO_CONTENT / "schema" / name).read_text(encoding="utf-8")
        assert committed == text, f"{name} is stale: run `make content-schema`"
