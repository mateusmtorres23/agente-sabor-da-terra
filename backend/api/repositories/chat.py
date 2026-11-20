from collections.abc import Sequence
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..agents.config import PERNAMBUCO_TIMEZONE, to_pernambuco_date
from ..models.chat_message import ChatMessage, ChatMessageFlow, ChatMessageRole
from ..models.chat_session import ChatSession
from ..models.citation import Citation
from ..models.document import DocumentChunk
from ..models.lot import Lot
from ..models.lot_draft import LotDraft


def normalize_message_reference_timestamp(
    value: datetime | date | str | None,
) -> datetime | None:
    """Converte data/data-hora de referência para timestamptz sem deslocar o dia em Pernambuco."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value
        return value.replace(tzinfo=PERNAMBUCO_TIMEZONE)
    if isinstance(value, date):
        return datetime(
            value.year,
            value.month,
            value.day,
            tzinfo=PERNAMBUCO_TIMEZONE,
        )
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        if "T" in cleaned or " " in cleaned:
            parsed_dt = datetime.fromisoformat(cleaned)
            if parsed_dt.tzinfo is not None:
                return parsed_dt
            return parsed_dt.replace(tzinfo=PERNAMBUCO_TIMEZONE)
        parsed_date = to_pernambuco_date(cleaned)
        return datetime(
            parsed_date.year,
            parsed_date.month,
            parsed_date.day,
            tzinfo=PERNAMBUCO_TIMEZONE,
        )
    raise TypeError(f"Unsupported reference timestamp value: {type(value)!r}")


def _normalize_flow(value: ChatMessageFlow | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, ChatMessageFlow):
        return value.value
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    return ChatMessageFlow(cleaned).value


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(self, user_id: UUID) -> ChatSession:
        chat = ChatSession(user_id=user_id)
        self.session.add(chat)
        await self.session.flush()
        return chat

    async def list_sessions(self, user_id: UUID) -> list[ChatSession]:
        statement = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.created_at.desc())
        )
        return list((await self.session.scalars(statement)).all())

    async def get_session(
        self,
        session_id: UUID,
        user_id: UUID,
        *,
        lock: bool = False,
    ) -> ChatSession | None:
        statement = (
            select(ChatSession)
            .where(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id,
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update(of=ChatSession)
        return await self.session.scalar(statement)
    async def get_session_for_user(
        self,
        session_id: UUID,
        user_id: UUID,
    ) -> ChatSession | None:
        return await self.get_session(session_id, user_id)
    
    async def get_session_by_id(self, session_id: UUID) -> ChatSession | None:
        return await self.session.get(ChatSession, session_id)

    async def add_message(
        self,
        session_id: UUID,
        content: str,
        *,
        role: ChatMessageRole = ChatMessageRole.USER,
        flow: ChatMessageFlow | str | None = None,
        reference_received_at: datetime | date | str | None = None,
    ) -> ChatMessage:
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("Message content must not be blank.")

        next_position = await self.session.scalar(
            select(func.coalesce(func.max(ChatMessage.position), 0) + 1)
            .where(ChatMessage.session_id == session_id)
        )
        message = ChatMessage(
            session_id=session_id,
            content=normalized_content,
            role=role,
            position=next_position,
            flow=_normalize_flow(flow),
            reference_received_at=normalize_message_reference_timestamp(
                reference_received_at
            ),
            citations=[],
            lot_draft=None,
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def add_citation(
        self,
        message_id: UUID,
        chunk_id: UUID,
    ) -> Citation:
        citation = Citation(message_id=message_id, chunk_id=chunk_id)
        self.session.add(citation)
        await self.session.flush()
        return citation

    async def add_message_with_citations(
        self,
        session_id: UUID,
        content: str,
        *,
        role: ChatMessageRole = ChatMessageRole.AGENT,
        chunk_ids: Sequence[UUID] = (),
        flow: ChatMessageFlow | str | None = None,
        reference_received_at: datetime | date | str | None = None,
    ) -> ChatMessage:
        """Persiste mensagem e citações via flush na mesma transação ativa."""
        msg = await self.add_message(
            session_id,
            content,
            role=role,
            flow=flow,
            reference_received_at=reference_received_at,
        )
        seen_chunk_ids: set[UUID] = set()
        for chunk_id in chunk_ids:
            if chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk_id)
            await self.add_citation(msg.id, chunk_id)

        if seen_chunk_ids:
            loaded = await self.get_message_with_citations(msg.id)
            if loaded is not None:
                return loaded
        return msg

    async def get_message_with_citations(
        self,
        message_id: UUID,
    ) -> ChatMessage | None:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.id == message_id)
            .options(
                selectinload(ChatMessage.citations)
                .selectinload(Citation.chunk)
                .selectinload(DocumentChunk.document),
                selectinload(ChatMessage.lot_draft).selectinload(LotDraft.order),
                selectinload(ChatMessage.lot_draft)
                .selectinload(LotDraft.lot)
                .selectinload(Lot.producer),
                selectinload(ChatMessage.lot_draft)
                .selectinload(LotDraft.lot)
                .selectinload(Lot.item),
            )
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(stmt)
    
    async def list_messages(self, session_id: UUID) -> list[ChatMessage]:
        statement = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .options(
                selectinload(ChatMessage.citations)
                .selectinload(Citation.chunk)
                .selectinload(DocumentChunk.document),
                selectinload(ChatMessage.lot_draft).selectinload(LotDraft.order),
                selectinload(ChatMessage.lot_draft)
                .selectinload(LotDraft.lot)
                .selectinload(Lot.producer),
                selectinload(ChatMessage.lot_draft)
                .selectinload(LotDraft.lot)
                .selectinload(Lot.item),
            )
            .order_by(
                ChatMessage.position.asc(),
                ChatMessage.created_at.asc(),
                ChatMessage.id.asc(),
            )
            .execution_options(populate_existing=True)
        )
        return list((await self.session.scalars(statement)).all())