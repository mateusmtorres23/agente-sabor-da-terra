from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.order_draft import OrderDraft


class OrderDraftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, draft: OrderDraft) -> None:
        self.session.add(draft)

    async def get_by_id(
        self,
        draft_id: UUID,
        *,
        session_id: UUID,
        lock: bool = False,
    ) -> OrderDraft | None:
        statement = (
            select(OrderDraft)
            .where(
                OrderDraft.id == draft_id,
                OrderDraft.session_id == session_id,
            )
            .execution_options(populate_existing=True)
        )

        if lock:
            statement = statement.with_for_update(of=OrderDraft)

        return await self.session.scalar(statement)

    async def get_latest_for_session(
        self,
        session_id: UUID,
    ) -> OrderDraft | None:
        statement = (
            select(OrderDraft)
            .where(OrderDraft.session_id == session_id)
            .order_by(
                OrderDraft.created_at.desc(),
                OrderDraft.id.desc(),
            )
            .limit(1)
            .execution_options(populate_existing=True)
        )

        return await self.session.scalar(statement)

    async def get_confirmed_for_session(
        self,
        session_id: UUID,
    ) -> OrderDraft | None:
        statement = (
            select(OrderDraft)
            .where(
                OrderDraft.session_id == session_id,
                OrderDraft.confirmed_order_id.is_not(None),
            )
            .execution_options(populate_existing=True)
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()