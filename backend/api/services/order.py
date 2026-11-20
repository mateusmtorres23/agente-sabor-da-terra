from decimal import Decimal
from uuid import UUID

from ..helpers.units import sum_quantities_in_unit
from ..models.order import Order
from ..models.order_item import OrderItem
from ..models.product import Product
from ..repositories.order import OrderRepository
from ..repositories.product import ProductRepository
from ..schemas.order import (
    OrderCreate,
    OrderItemCreate,
    OrderItemUpdate,
    OrderUpdate,
)


class OrderNotFoundError(LookupError):
    pass


class OrderCancelledError(ValueError):
    pass


class OrderConflictError(ValueError):
    pass


class OrderValidationError(ValueError):
    pass


class OrderService:
    def __init__(
        self,
        repository: OrderRepository,
        product_repository: ProductRepository,
    ) -> None:
        self.repository = repository
        self.product_repository = product_repository

    async def list_orders(self) -> list[Order]:
        return await self.repository.list_all()

    async def get_order(
        self,
        order_id: UUID,
        *,
        lock: bool = False,
    ) -> Order:
        order = await self.repository.get_by_id(
            order_id,
            lock=lock,
        )

        if order is None:
            raise OrderNotFoundError("Pedido não encontrado.")

        return order

    async def _get_products(
        self,
        items: list[OrderItemCreate] | list[OrderItemUpdate],
    ) -> dict[UUID, Product]:
        products: dict[UUID, Product] = {}

        for item in items:
            if item.product_id in products:
                continue

            product = await self.product_repository.get_by_id(
                item.product_id
            )

            if product is None:
                raise OrderValidationError(
                    f"Produto não encontrado: {item.product_id}."
                )

            products[item.product_id] = product

        return products

    def _create_item(
        self,
        data: OrderItemCreate,
        product: Product,
    ) -> OrderItem:
        return OrderItem(
            product_id=product.id,
            product=product,
            quantity=data.quantity,
            unit=data.unit,
            lots=[],
        )

    async def create_order(
        self,
        data: OrderCreate,
        *,
        session_id: UUID | None = None,
        commit: bool = True,
    ) -> Order:
        try:
            products = await self._get_products(data.items)

            order = Order(
                session_id=session_id,
                buyer=data.buyer,
                products="",
                conditions=data.conditions,
                delivery_start_date=data.delivery_start_date,
                delivery_end_date=data.delivery_end_date,
                items=[
                    self._create_item(
                        item,
                        products[item.product_id],
                    )
                    for item in data.items
                ],
            )

            self.repository.add(order)

            if commit:
                await self.repository.session.commit()
            else:
                await self.repository.session.flush()

            return order

        except Exception:
            await self.repository.session.rollback()
            raise

    async def update_order(
        self,
        order_id: UUID,
        data: OrderUpdate,
    ) -> Order:
        try:
            order = await self.get_order(
                order_id,
                lock=True,
            )

            if order.cancelled:
                raise OrderCancelledError(
                    "Um pedido cancelado não pode ser editado."
                )

            # Check only after obtaining the row lock and loading the current state.
            # A second writer waiting on the lock must compare against the new version.
            if data.version != order.version:
                raise OrderConflictError(
                    "Este pedido foi alterado desde que o formulário foi aberto. "
                    "Recarregue o pedido e revise suas alterações antes de salvar."
                )

            existing_items = {
                item.id: item
                for item in order.items
            }

            for item_data in data.items:
                if (
                    item_data.id is not None
                    and item_data.id not in existing_items
                ):
                    raise OrderValidationError(
                        "Um dos itens informados não pertence a este pedido."
                    )

            products = await self._get_products(data.items)

            self._ensure_allocations_still_valid(order, existing_items, data)

            updated_items: list[OrderItem] = []

            for item_data in data.items:
                product = products[item_data.product_id]

                if item_data.id is None:
                    item = self._create_item(
                        item_data,
                        product,
                    )
                else:
                    item = existing_items[item_data.id]

                    item.product_id = product.id
                    item.product = product
                    item.quantity = item_data.quantity
                    item.unit = item_data.unit

                updated_items.append(item)

            order.buyer = data.buyer
            order.conditions = data.conditions
            order.delivery_start_date = data.delivery_start_date
            order.delivery_end_date = data.delivery_end_date

            order.items = updated_items
            order.version += 1

            await self.repository.session.commit()

            return order

        except Exception:
            await self.repository.session.rollback()
            raise

    async def cancel_order(self, order_id: UUID) -> Order:
        try:
            order = await self.get_order(
                order_id,
                lock=True,
            )

            if not order.cancelled:
                order.cancelled = True
                order.version += 1

                for item in order.items:
                    for lot in list(item.lots):
                        await self.repository.session.delete(lot)
                    item.lots.clear()

            await self.repository.session.commit()

            return order

        except Exception:
            await self.repository.session.rollback()
            raise

    def _ensure_allocations_still_valid(
        self,
        order: Order,
        existing_items: dict[UUID, OrderItem],
        data: OrderUpdate,
    ) -> None:
        incoming_ids = {
            item_data.id
            for item_data in data.items
            if item_data.id is not None
        }
        removed_ids = set(existing_items) - incoming_ids

        for item_id in removed_ids:
            item = existing_items[item_id]
            if item.lots:
                raise OrderValidationError(
                    "O item possui alocações operacionais. Exclua as "
                    "alocações antes de remover o item do pedido."
                )

        for item_data in data.items:
            if item_data.id is None:
                continue
            item = existing_items[item_data.id]

            if (
                item.product_id != item_data.product_id
                or item.unit != item_data.unit
            ) and item.lots:
                raise OrderValidationError(
                    "O produto ou a unidade do item possui alocações "
                    "operacionais. Ajuste ou exclua as alocações antes "
                    "de salvar."
                )

            if item.quantity > item_data.quantity:
                allocated = self._allocated_in_item_unit(item)
                if allocated is not None and allocated > item_data.quantity:
                    raise OrderValidationError(
                        "A nova quantidade do item é menor que o total já "
                        "alocado. Ajuste ou exclua as alocações antes de "
                        "salvar."
                    )

        start = data.delivery_start_date
        end = data.delivery_end_date or data.delivery_start_date

        for item in existing_items.values():
            for lot in item.lots:
                if not (start <= lot.delivery_date <= end):
                    raise OrderValidationError(
                        f"A data {lot.delivery_date.isoformat()} de uma "
                        "alocação ficou fora do novo prazo de entrega "
                        f"({start.isoformat()} a {end.isoformat()}). Ajuste "
                        "ou exclua a alocação antes de salvar."
                    )

    def _allocated_in_item_unit(self, item: OrderItem) -> Decimal | None:
        return sum_quantities_in_unit(
            [(lot.quantity, lot.unit) for lot in item.lots],
            item.unit,
        )