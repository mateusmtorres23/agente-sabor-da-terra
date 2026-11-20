from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.chat_message import ChatMessage, ChatMessageRole
from ..models.chat_session import ChatSession
from ..models.citation import Citation
from ..models.document import DocumentChunk
from ..models.lot import Lot
from ..models.lot_draft import LotDraft


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
        self, session_id: UUID, user_id: UUID
    ) -> ChatSession | None:
        """Usado pelo LotDraftService para validar que a conversa é do usuário."""
        return await self.get_session(session_id, user_id)

    async def get_session_for_user(
        self, session_id: UUID, user_id: UUID
    ) -> ChatSession | None:
        """Usado pelo LotDraftService para validar que a conversa é do usuário."""
        return await self.get_session(session_id, user_id)

    async def add_message(
        self,
        session_id: UUID,
        content: str,
        *,
        role: ChatMessageRole = ChatMessageRole.USER,
    ) -> ChatMessage:
        next_position = await self.session.scalar(
            select(func.coalesce(func.max(ChatMessage.position), 0) + 1)
            .where(ChatMessage.session_id == session_id)
        )
        message = ChatMessage(
            session_id=session_id,
            content=content,
            role=role,
            position=next_position,
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
        )
        return list((await self.session.scalars(statement)).all())