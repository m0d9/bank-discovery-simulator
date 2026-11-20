"""Build public DTOs from content models, field by field.

Never `model_dump` a content model into a response: copying fields one at a time means a new
private field can't reach the API by accident.
"""

from app.api.dto import (
    AnalysisDTO,
    BankDTO,
    ClientCardDTO,
    CoachReportDTO,
    FactResultDTO,
    FactUnlockDTO,
    FeedbackDTO,
    FeedbackStatsDTO,
    ImprovementDTO,
    LocalizedTextDTO,
    MessageResultDTO,
    MissedOpportunityDTO,
    MissedPointDTO,
    NeedResultDTO,
    NeedViaDTO,
    PersonaDTO,
    ProductDTO,
    ProductVerdictDTO,
    RecommendationDTO,
    RevealedClientDTO,
    RevealedFactDTO,
    RevealedNeedDTO,
    SessionCreatedDTO,
    SessionModelsDTO,
    SessionPublicDTO,
    SubmittedWrapUpDTO,
    TurnDTO,
    UnsuitableProductDTO,
    VerdictReasonDTO,
    WentWellDTO,
)
from app.coaching import Analysis, CoachReport, Feedback
from app.config import Settings
from app.content import Bank, Client, LocalizedText, Product
from app.simulation import Session, SessionModels, Turn, TurnResult, WrapUp


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


def feedback_dto(session: Session, feedback: Feedback) -> FeedbackDTO:
    """The feedback, with the client's private profile: shown once the session has feedback."""
    if session.wrapup is None:
        raise ValueError("feedback needs a wrapped-up session")
    return FeedbackDTO(
        session_id=session.id,
        language=feedback.language,
        analysis=analysis_dto(feedback.analysis),
        report=coach_report_dto(feedback.report) if feedback.report is not None else None,
        degraded=feedback.degraded,
        models=session_models_dto(session.models),
        generated_at=feedback.generated_at,
        wrapup=submitted_wrapup_dto(session.wrapup),
        revealed=revealed_client_dto(session.client, feedback.analysis),
    )


def submitted_wrapup_dto(wrapup: WrapUp) -> SubmittedWrapUpDTO:
    return SubmittedWrapUpDTO(
        needs_summary=wrapup.needs_summary,
        recommendations=[
            RecommendationDTO(product_id=item.product_id, reason=item.reason)
            for item in wrapup.recommendations
        ],
    )


def analysis_dto(analysis: Analysis) -> AnalysisDTO:
    return AnalysisDTO(
        needs=[
            NeedResultDTO(
                need_id=need.need_id,
                status=need.status,
                facts=[
                    FactUnlockDTO(fact_id=fact.fact_id, unlocked_at_turn=fact.unlocked_at_turn)
                    for fact in need.facts
                ],
                via=NeedViaDTO(turn=need.via.turn, question=need.via.question)
                if need.via is not None
                else None,
            )
            for need in analysis.needs
        ],
        facts=[
            FactResultDTO(
                fact_id=fact.fact_id,
                importance=fact.importance,
                unlocked_at_turn=fact.unlocked_at_turn,
                discovered_by=fact.discovered_by,
            )
            for fact in analysis.facts
        ],
        products=[
            ProductVerdictDTO(
                product_id=verdict.product_id,
                verdict=verdict.verdict,
                reasons=[
                    VerdictReasonDTO(need_id=reason.need_id, reason=localized_dto(reason.reason))
                    for reason in verdict.reasons
                ],
                needs=list(verdict.needs),
                ruled_out_at=verdict.ruled_out_at,
                pitched_at=verdict.pitched_at,
            )
            for verdict in analysis.products
        ],
        missed_opportunities=[
            MissedOpportunityDTO(product_id=item.product_id, needs=list(item.needs))
            for item in analysis.missed_opportunities
        ],
        stats=FeedbackStatsDTO(
            student_turns=analysis.stats.student_turns,
            needs_uncovered=analysis.stats.needs_uncovered,
            needs_after_pitch=analysis.stats.needs_after_pitch,
            needs_total=analysis.stats.needs_total,
            critical_found=analysis.stats.critical_found,
            critical_total=analysis.stats.critical_total,
            first_unlock_turn=analysis.stats.first_unlock_turn,
        ),
    )


def coach_report_dto(report: CoachReport) -> CoachReportDTO:
    return CoachReportDTO(
        went_well=[
            WentWellDTO(point=item.point, evidence_turns=list(item.evidence_turns))
            for item in report.went_well
        ],
        missed=[
            MissedPointDTO(
                point=item.point,
                need_id=item.need_id,
                product_id=item.product_id,
                evidence_turns=list(item.evidence_turns),
                better_question=item.better_question,
            )
            for item in report.missed
        ],
        how_to_improve=[
            ImprovementDTO(tip=item.tip, example=item.example) for item in report.how_to_improve
        ],
        summary_feedback=report.summary_feedback,
    )


def revealed_client_dto(client: Client, analysis: Analysis) -> RevealedClientDTO:
    """The private profile, field by field. Persona and fact texts are English-only content."""
    persona = client.persona
    unlocked = {fact.fact_id: fact.unlocked_at_turn for fact in analysis.facts}
    status = {need.need_id: need.status for need in analysis.needs}
    return RevealedClientDTO(
        persona=PersonaDTO(
            age=persona.age,
            occupation=_english(persona.occupation),
            nationality=_english(persona.nationality),
            family=_english(persona.family) if persona.family is not None else None,
            background=_english(persona.background),
            personality=_english(persona.personality),
            speaking_style=_english(persona.speaking_style),
            financial_knowledge=persona.financial_knowledge,
        ),
        open_facts=[_english(fact) for fact in client.open_facts],
        hidden_facts=[
            RevealedFactDTO(
                id=fact.id,
                content=_english(fact.content),
                importance=fact.importance,
                unlocked_at_turn=unlocked.get(fact.id),
            )
            for fact in client.hidden_facts
        ],
        needs=[
            RevealedNeedDTO(
                id=need.id,
                description=localized_dto(need.description),
                status=status[need.id],
                suitable_products=list(need.suitable_products),
                unsuitable_products=[
                    UnsuitableProductDTO(id=entry.id, reason=localized_dto(entry.reason))
                    for entry in need.unsuitable_products
                ],
            )
            for need in client.needs
        ],
        no_catalogue_fit=client.no_catalogue_fit,
        referral_note=localized_dto(client.referral_note)
        if client.referral_note is not None
        else None,
    )


def _english(text: str) -> LocalizedTextDTO:
    return LocalizedTextDTO(en=text, ar=None)
