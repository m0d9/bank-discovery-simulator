"""Build public DTOs from content models, field by field.

Never `model_dump` a content model into a response: copying fields one at a time means a new
private field can't reach the API by accident.
"""

from app.api.dto import (
    BankDTO,
    ClientCardDTO,
    LocalizedTextDTO,
    MessageResultDTO,
    ProductDTO,
    SessionCreatedDTO,
    SessionModelsDTO,
    SessionPublicDTO,
    TurnDTO,
)
from app.config import Settings
from app.content import Bank, Client, LocalizedText, Product
from app.simulation import Session, SessionModels, Turn, TurnResult


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


def session_models_dto(models: SessionModels) -> SessionModelsDTO:
    return SessionModelsDTO(gate=models.gate, client=models.client, coach=models.coach)


def turn_dto(turn: Turn) -> TurnDTO:
    """The number, speaker and text only: never the facts a message unlocked."""
    return TurnDTO(n=turn.n, role=turn.role, text=turn.text)


def session_created_dto(session: Session, settings: Settings) -> SessionCreatedDTO:
    return SessionCreatedDTO(
        session_id=session.id,
        client=client_card_dto(session.client),
        opening_line=localized_dto(session.client.card.opening_line),
        max_student_turns=settings.MAX_STUDENT_TURNS,
        max_message_chars=settings.MAX_MESSAGE_CHARS,
        models=session_models_dto(session.models),
    )


def session_public_dto(session: Session, settings: Settings) -> SessionPublicDTO:
    return SessionPublicDTO(
        session_id=session.id,
        client=client_card_dto(session.client),
        status=session.status,
        language=session.language,
        turns=[turn_dto(turn) for turn in session.turns],
        student_turns_used=session.student_turns_used,
        max_student_turns=settings.MAX_STUDENT_TURNS,
        max_message_chars=settings.MAX_MESSAGE_CHARS,
        models=session_models_dto(session.models),
    )


def message_result_dto(result: TurnResult, settings: Settings) -> MessageResultDTO:
    return MessageResultDTO(
        student_turn=turn_dto(result.student_turn),
        client_turn=turn_dto(result.client_turn),
        student_turns_used=result.session.student_turns_used,
        max_student_turns=settings.MAX_STUDENT_TURNS,
    )
