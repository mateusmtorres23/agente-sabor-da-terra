from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.chat_message import ChatMessage, ChatMessageFlow, ChatMessageRole
from ..models.chat_session import ChatSession
from ..models.solicitation import Solicitation
from .chat import ChatRepository


class SolicitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.chat_repository = ChatRepository(session)

    def add(self, solicitation: Solicitation) -> None:
        self.session.add(solicitation)

    async def create_session(self, title: str) -> ChatSession:
        chat = ChatSession(user_id=None, title=title)
        self.session.add(chat)
        await self.session.flush()
        return chat

    async def get_session(
        self,
        session_id: UUID,
        *,
        lock: bool = False,
    ) -> ChatSession | None:
        statement = (
            select(ChatSession)
            .where(ChatSession.id == session_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update(of=ChatSession)
        return await self.session.scalar(statement)

    async def list_all(self) -> list[Solicitation]:
        statement = (
            select(Solicitation)
            .join(ChatSession, Solicitation.session_id == ChatSession.id)
            .order_by(
                ChatSession.created_at.desc(),
                Solicitation.id.desc(),
            )
        )
        return list((await self.session.scalars(statement)).all())

    async def get_by_id(
        self,
        solicitation_id: UUID,
        *,
        lock: bool = False,
    ) -> Solicitation | None:
        statement = (
            select(Solicitation)
            .where(Solicitation.id == solicitation_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def add_message(
        self,
        session_id: UUID,
        content: str,
        *,
        role: ChatMessageRole = ChatMessageRole.USER,
        flow: ChatMessageFlow | str | None = None,
        reference_received_at: datetime | date | str | None = None,
    ) -> ChatMessage:
        return await self.chat_repository.add_message(
            session_id,
            content,
            role=role,
            flow=flow,
            reference_received_at=reference_received_at,
        )

    async def list_messages(self, session_id: UUID) -> list[ChatMessage]:
        return await self.chat_repository.list_messages(session_id)