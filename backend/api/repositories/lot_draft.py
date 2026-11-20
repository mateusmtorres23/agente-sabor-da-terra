from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.lot import Lot
from ..models.lot_draft import LotDraft
from ..models.order import Order
from ..models.order_item import OrderItem


class LotDraftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, draft: LotDraft) -> None:
        self.session.add(draft)

    async def get_by_id(
        self,
        draft_id: UUID,
        *,
        lock: bool = False,
        with_relations: bool = True,
    ) -> LotDraft | None:
        stmt = select(LotDraft).where(LotDraft.id == draft_id)
        if lock:
            stmt = stmt.with_for_update()
        if with_relations:
            stmt = stmt.options(
                selectinload(LotDraft.order).selectinload(Order.items).selectinload(OrderItem.product),
                selectinload(LotDraft.order).selectinload(Order.items).selectinload(OrderItem.lots).selectinload(Lot.producer),
                selectinload(LotDraft.item).selectinload(OrderItem.product),
                selectinload(LotDraft.item).selectinload(OrderItem.lots).selectinload(Lot.producer),
                selectinload(LotDraft.producer),
                selectinload(LotDraft.lot).selectinload(Lot.producer),
                selectinload(LotDraft.lot).selectinload(Lot.producer),
                selectinload(LotDraft.lot).selectinload(Lot.item),
            )
        return await self.session.scalar(stmt)