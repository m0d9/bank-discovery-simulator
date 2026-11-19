"""Build public DTOs from content models, field by field.

Never `model_dump` a content model into a response: copying fields one at a time means a new
private field can't reach the API by accident.
"""

from app.api.dto import BankDTO, ClientCardDTO, LocalizedTextDTO, ProductDTO
from app.content import Bank, Client, LocalizedText, Product


def localized_dto(text: LocalizedText) -> LocalizedTextDTO:
    return LocalizedTextDTO(en=text.en, ar=text.ar)


def bank_dto(bank: Bank) -> BankDTO:
    return BankDTO(
        name=localized_dto(bank.name),
        tagline=localized_dto(bank.tagline),
        disclaimer=localized_dto(bank.disclaimer),
        currency=bank.currency,
    )


def client_card_dto(client: Client) -> ClientCardDTO:
    """The public card only: no persona, facts, needs or coach notes."""
    return ClientCardDTO(
        id=client.id,
        segment=client.segment,
        difficulty=client.difficulty,
        name=localized_dto(client.card.name),
        headline=localized_dto(client.card.headline),
    )


def product_dto(product: Product) -> ProductDTO:
    """Everything a student may read about a product (not `client_view`, the model's line)."""
    return ProductDTO(
        id=product.id,
        name=localized_dto(product.name),
        summary=localized_dto(product.summary),
        segments=list(product.segments),
        category=product.category,
        sharia_compliant=product.sharia_compliant,
        interest_based=product.interest_based,
        features=[localized_dto(text) for text in product.features],
        limitations=[localized_dto(text) for text in product.limitations],
        eligibility=[localized_dto(text) for text in product.eligibility],
        pricing=localized_dto(product.pricing),
    )
