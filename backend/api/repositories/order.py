from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.lot import Lot
from ..models.order import Order
from ..models.order_item import OrderItem


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, order: Order) -> None:
        self.session.add(order)

    async def list_all(self) -> list[Order]:
        statement = (
            select(Order)
            .options(
                selectinload(Order.items)
                .selectinload(OrderItem.product),
                selectinload(Order.items)
                .selectinload(OrderItem.lots)
                .selectinload(Lot.producer),
            )
            .order_by(Order.id)
        )

        result = await self.session.scalars(statement)

        return list(result)

    async def get_by_id(
        self,
        order_id: UUID,
        *,
        lock: bool = False,
    ) -> Order | None:
        statement = (
            select(Order)
            .where(Order.id == order_id)
            .options(
                selectinload(Order.items)
                .selectinload(OrderItem.product),
                selectinload(Order.items)
                .selectinload(OrderItem.lots)
                .selectinload(Lot.producer),
            )
            .execution_options(populate_existing=True)
        )

        if lock:
            statement = statement.with_for_update(of=Order)

        return await self.session.scalar(statement)

    async def get_by_item_id(
        self,
        item_id: UUID,
        *,
        lock: bool = False,
    ) -> Order | None:
        statement = (
            select(Order)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .where(OrderItem.id == item_id)
            .options(
                selectinload(Order.items)
                .selectinload(OrderItem.product),
                selectinload(Order.items)
                .selectinload(OrderItem.lots)
                .selectinload(Lot.producer),
            )
            .execution_options(populate_existing=True)
        )

        if lock:
            statement = statement.with_for_update(of=Order)

        return await self.session.scalar(statement)

    async def get_by_session(
        self,
        session_id: UUID,
    ) -> Order | None:
        statement = (
            select(Order)
            .where(Order.session_id == session_id)
            .options(
                selectinload(Order.items)
                .selectinload(OrderItem.product),
                selectinload(Order.items)
                .selectinload(OrderItem.lots)
                .selectinload(Lot.producer),
            )
            .execution_options(populate_existing=True)
        )

        return await self.session.scalar(statement)
