import pytest

from app.content import ContentRegistry, UnknownClient, UnknownProduct, load_registry
from tests.content_factory import ALPHA, BETA, CLIENT, ContentDir, client_data


def test_valid_content_loads_with_the_right_counts(content: ContentDir) -> None:
    registry = load_registry(content.root)

    assert isinstance(registry, ContentRegistry)
    assert registry.bank.name.en == "Test Bank"
    assert [product.id for product in registry.list_products()] == [ALPHA, BETA]
    assert [client.id for client in registry.list_clients()] == [CLIENT]


def test_lookups_return_the_model_or_raise_a_typed_error(content: ContentDir) -> None:
    registry = load_registry(content.root)

    assert registry.get_client(CLIENT).card.name.ar == "عميل الاختبار"
    assert registry.get_product(BETA).sharia_compliant is True
    with pytest.raises(UnknownClient) as client_error:
        registry.get_client("nobody")
    assert client_error.value.client_id == "nobody"
    with pytest.raises(UnknownProduct):
        registry.get_product("nothing")
    assert issubclass(UnknownClient, LookupError) and issubclass(UnknownProduct, LookupError)


def test_clients_are_listed_easiest_first_then_by_id(content: ContentDir) -> None:
    for client_id, difficulty in [("b-hard", "hard"), ("a-medium", "medium"), ("z-easy", "easy")]:
        content.write(f"clients/{client_id}.yaml", client_data(client_id, difficulty=difficulty))

    ids = [client.id for client in load_registry(content.root).list_clients()]

    assert ids == [CLIENT, "z-easy", "a-medium", "b-hard"]
