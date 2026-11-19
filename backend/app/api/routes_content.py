"""Public content: the bank, the client cards and the product catalogue. Read-only."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dto import BankDTO, ClientCardDTO, ProductDTO
from app.api.mappers import bank_dto, client_card_dto, product_dto
from app.content import ContentRegistry, get_registry

router = APIRouter(tags=["content"])

Registry = Annotated[ContentRegistry, Depends(get_registry)]


@router.get("/bank", response_model=BankDTO)
async def bank(registry: Registry) -> BankDTO:
    """The fictional bank's name, tagline, disclaimer and currency."""
    return bank_dto(registry.bank)


@router.get("/clients", response_model=list[ClientCardDTO])
async def clients(registry: Registry) -> list[ClientCardDTO]:
    """Every client's public card, easiest first."""
    return [client_card_dto(client) for client in registry.list_clients()]


@router.get("/products", response_model=list[ProductDTO])
async def products(registry: Registry) -> list[ProductDTO]:
    """The product catalogue, by id."""
    return [product_dto(product) for product in registry.list_products()]
