from uuid import UUID, uuid4

from ..helpers.triage import (
    build_triage_session_title,
    format_triage_analysis,
)
from ..models.chat_message import ChatMessage, ChatMessageFlow, ChatMessageRole
from ..models.chat_session import ChatSession
from ..models.solicitation import (
    Solicitation,
    SolicitationStatus,
    SolicitationType,
    SolicitationUrgency,
)
from ..repositories.solicitation import SolicitationRepository
from ..schemas.solicitation import SolicitationCreate


class SolicitationNotFoundError(LookupError):
    pass


class SolicitationFinishedError(ValueError):
    pass


class SolicitationService:
    def __init__(self, repository: SolicitationRepository) -> None:
        self.repository = repository

    async def persist_from_analysis(
        self,
        payload: SolicitationCreate,
        *,
        solicitation_id: UUID | None = None,
    ) -> Solicitation:
        analysis = payload.analysis
        chat = await self.repository.create_session(
            build_triage_session_title(payload.input, analysis)
        )
        await self.repository.add_message(
            chat.id,
            payload.input.message_text,
            role=ChatMessageRole.USER,
            flow=ChatMessageFlow.TRIAGE,
            reference_received_at=payload.input.received_at,
        )
        analysis_ref_received_at = (
            payload.input.received_at
            if payload.input.received_date.isoformat() == analysis.received_date_reference
            else analysis.received_date_reference
        )
        await self.repository.add_message(
            chat.id,
            format_triage_analysis(analysis),
            role=ChatMessageRole.AGENT,
            flow=ChatMessageFlow.TRIAGE,
            reference_received_at=analysis_ref_received_at,
        )

        solicitation = Solicitation(
            id=solicitation_id or uuid4(),
            status=SolicitationStatus.RECEIVED,
            summary=analysis.summary,
            request_type=SolicitationType(analysis.request_type.value),
            urgency=SolicitationUrgency(analysis.urgency.value),
            session_id=chat.id,
        )
        self.repository.add(solicitation)
        await self.repository.session.flush()
        return solicitation

    async def create_from_analysis(
        self,
        payload: SolicitationCreate,
        *,
        solicitation_id: UUID | None = None,
    ) -> Solicitation:
        try:
            solicitation = await self.persist_from_analysis(
                payload,
                solicitation_id=solicitation_id or payload.id,
            )
        except Exception:
            await self._rollback()
            raise

        await self._commit()
        return solicitation

    async def list_solicitations(self) -> list[Solicitation]:
        return await self.repository.list_all()

    async def get_solicitation(self, solicitation_id: UUID) -> Solicitation:
        return await self._get_solicitation(solicitation_id)

    async def open_session(
        self,
        solicitation_id: UUID,
    ) -> tuple[Solicitation, ChatSession, list[ChatMessage], bool]:
        solicitation = await self._get_solicitation(
            solicitation_id,
            lock=True,
        )

        read_only = solicitation.status == SolicitationStatus.FINISHED
        if solicitation.status == SolicitationStatus.RECEIVED:
            solicitation.status = SolicitationStatus.IN_REVIEW

        await self._commit()

        chat = await self.repository.get_session(solicitation.session_id)
        if chat is None:
            raise SolicitationNotFoundError("Sessão não encontrada.")
        messages = await self.repository.list_messages(solicitation.session_id)
        return solicitation, chat, messages, read_only

    async def add_message(
        self,
        solicitation_id: UUID,
        content: str,
    ) -> ChatMessage:
        solicitation = await self._get_solicitation(
            solicitation_id,
            lock=True,
        )
        if solicitation.status == SolicitationStatus.FINISHED:
            raise SolicitationFinishedError(
                "A conversa está finalizada e não aceita novas mensagens."
            )

        if solicitation.status == SolicitationStatus.RECEIVED:
            solicitation.status = SolicitationStatus.IN_REVIEW

        try:
            message = await self.repository.add_message(
                solicitation.session_id,
                content,
            )
        except Exception:
            await self._rollback()
            raise

        await self._commit()
        return message

    async def finalize(self, solicitation_id: UUID) -> Solicitation:
        solicitation = await self._get_solicitation(
            solicitation_id,
            lock=True,
        )

        solicitation.status = SolicitationStatus.FINISHED
        await self._commit()
        return solicitation

    async def _get_solicitation(
        self,
        solicitation_id: UUID,
        *,
        lock: bool = False,
    ) -> Solicitation:
        solicitation = await self.repository.get_by_id(
            solicitation_id,
            lock=lock,
        )
        if solicitation is None:
            raise SolicitationNotFoundError("Solicitação não encontrada.")
        return solicitation

    async def _commit(self) -> None:
        try:
            await self.repository.session.commit()
        except Exception:
            await self._rollback()
            raise

    async def _rollback(self) -> None:
        await self.repository.session.rollback()
