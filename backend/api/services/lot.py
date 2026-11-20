from decimal import Decimal
from uuid import UUID

from ..helpers.units import (
    IncompatibleUnitError,
    convert_quantity,
    sum_quantities_in_unit,
)
from ..models.lot import Lot
from ..models.order import Order
from ..models.order_item import OrderItem
from ..models.producer import Producer
from ..repositories.lot import LotRepository
from ..repositories.order import OrderRepository
from ..repositories.producer import ProducerRepository
from ..schemas.lot import LotCreate, LotUpdate


class LotNotFoundError(LookupError):
    pass


class LotValidationError(ValueError):
    pass


class LotConflictError(ValueError):
    pass


class LotService:
    def __init__(
        self,
        repository: LotRepository,
        order_repository: OrderRepository,
        producer_repository: ProducerRepository,
    ) -> None:
        self.repository = repository
        self.order_repository = order_repository
        self.producer_repository = producer_repository

    async def create(
        self,
        order_id: UUID,
        item_id: UUID,
        data: LotCreate,
        *,
        commit: bool = True,
    ) -> Lot:
        try:
            order = await self._get_order(order_id, lock=True)
            item = self._find_item(order, item_id)
            self._ensure_active(order)

            producer = await self._get_active_producer(data.producer_id, item)
            self._validate_delivery_date(order, data.delivery_date)

            if not data.availability_confirmed:
                raise LotValidationError(
                    "Confirme a disponibilidade do produtor para salvar a alocação."
                )

            converted = self._convert_quantity(
                data.quantity,
                data.unit,
                item.unit,
            )
            allocated = self._allocated(item)
            self._ensure_balance(allocated, converted, item)

            lot = Lot(
                item_id=item.id,
                producer_id=producer.id,
                producer=producer,
                quantity=data.quantity,
                unit=data.unit,
                delivery_date=data.delivery_date,
                availability_confirmed=True,
            )
            self.repository.add(lot)
            if commit:
                await self._commit()
            else:
                await self.repository.session.flush()
            return lot

        except Exception:
            await self._rollback()
            raise

    async def update(self, lot_id: UUID, data: LotUpdate) -> Lot:
        try:
            existing = await self.repository.get_by_id(lot_id)
            if existing is None:
                raise LotNotFoundError("Lote não encontrado.")
            if existing.item_id is None:
                raise LotValidationError(
                    "Lotes importados não podem ser editados."
                )

            order = await self._get_order_by_item(existing.item_id, lock=True)
            self._ensure_active(order)
            item = self._find_item(order, existing.item_id)
            lot = self._find_lot(item, lot_id)
            if lot is None:
                raise LotNotFoundError("Lote não encontrado.")

            producer = await self._get_active_producer(data.producer_id, item)
            self._validate_delivery_date(order, data.delivery_date)

            changed = (
                lot.producer_id != data.producer_id
                or lot.quantity != data.quantity
                or lot.unit != data.unit
                or lot.delivery_date != data.delivery_date
            )
            if changed and not data.availability_confirmed:
                raise LotValidationError(
                    "Os dados da alocação mudaram. Confirme novamente a "
                    "disponibilidade do produtor para o fornecimento revisado."
                )

            converted = self._convert_quantity(
                data.quantity,
                data.unit,
                item.unit,
            )
            allocated = self._allocated(item, excluding=lot.id)
            self._ensure_balance(allocated, converted, item)

            lot.producer_id = producer.id
            lot.producer = producer
            lot.quantity = data.quantity
            lot.unit = data.unit
            lot.delivery_date = data.delivery_date
            lot.availability_confirmed = True

            await self._commit()
            return lot

        except Exception:
            await self._rollback()
            raise

    async def delete(self, lot_id: UUID) -> None:
        try:
            existing = await self.repository.get_by_id(lot_id)
            if existing is None:
                raise LotNotFoundError("Lote não encontrado.")
            if existing.item_id is None:
                raise LotValidationError(
                    "Lotes importados não podem ser excluídos."
                )

            order = await self._get_order_by_item(existing.item_id, lock=True)
            self._ensure_active(order)
            item = self._find_item(order, existing.item_id)
            lot = self._find_lot(item, lot_id)
            if lot is None:
                raise LotNotFoundError("Lote não encontrado.")

            await self.repository.delete(lot)
            await self._commit()

        except Exception:
            await self._rollback()
            raise

    async def _get_order(self, order_id: UUID, *, lock: bool) -> Order:
        order = await self.order_repository.get_by_id(order_id, lock=lock)
        if order is None:
            raise LotNotFoundError("Pedido não encontrado.")
        return order

    async def _get_order_by_item(self, item_id: UUID, *, lock: bool) -> Order:
        order = await self.order_repository.get_by_item_id(item_id, lock=lock)
        if order is None:
            raise LotNotFoundError("Item do pedido não encontrado.")
        return order

    def _find_item(self, order: Order, item_id: UUID) -> OrderItem:
        for item in order.items:
            if item.id == item_id:
                return item
        raise LotNotFoundError("Item não encontrado neste pedido.")

    def _find_lot(self, item: OrderItem, lot_id: UUID) -> Lot | None:
        for lot in item.lots:
            if lot.id == lot_id:
                return lot
        return None

    def _ensure_active(self, order: Order) -> None:
        if order.cancelled:
            raise LotConflictError(
                "O pedido está cancelado e não aceita novas alocações."
            )

    async def _get_active_producer(
        self,
        producer_id: UUID,
        item: OrderItem,
    ) -> Producer:
        producer = await self.producer_repository.get_by_id(producer_id)
        if producer is None:
            raise LotValidationError("Produtor não encontrado.")
        if not producer.active:
            raise LotValidationError(
                f"O produtor {producer.name} está inativo e não pode atender "
                "a este item."
            )
        if not await self.producer_repository.is_associated(
            producer.id,
            item.product_id,
        ):
            raise LotValidationError(
                f"O produtor {producer.name} não fornece o produto deste item."
            )
        return producer

    def _validate_delivery_date(self, order: Order, delivery_date) -> None:
        start = order.delivery_start_date
        end = order.delivery_end_date or start

        if start <= delivery_date <= end:
            return

        if start == end:
            raise LotValidationError(
                f"O pedido tem data única de entrega ({start.isoformat()}). "
                "A alocação deve usar essa data."
            )

        raise LotValidationError(
            f"A data {delivery_date.isoformat()} está fora do prazo de entrega "
            f"do pedido ({start.isoformat()} a {end.isoformat()})."
        )

    def _convert_quantity(
        self,
        quantity: Decimal,
        from_unit: str,
        to_unit: str,
    ) -> Decimal:
        try:
            return convert_quantity(quantity, from_unit, to_unit)
        except IncompatibleUnitError as error:
            raise LotValidationError(str(error)) from error

    def _allocated(
        self,
        item: OrderItem,
        *,
        excluding: UUID | None = None,
    ) -> Decimal | None:
        pairs = [
            (lot.quantity, lot.unit)
            for lot in item.lots
            if lot.id != excluding
        ]
        return sum_quantities_in_unit(pairs, item.unit)

    def _ensure_balance(
        self,
        allocated: Decimal | None,
        converted: Decimal,
        item: OrderItem,
    ) -> None:
        if allocated is None:
            raise LotValidationError(
                "O saldo deste item está indeterminado. Ajuste as unidades das "
                "alocações antes de salvar."
            )
        available = item.quantity - allocated
        if converted > available:
            formatted_available = f"{available.normalize():f}" if available != 0 else "0"
            raise LotValidationError(
                f"A quantidade solicitada ultrapassa o saldo disponível do item "
                f"(saldo atual: {formatted_available} {item.unit})."
            )

    async def _commit(self) -> None:
        try:
            await self.repository.session.commit()
        except Exception:
            await self._rollback()
            raise

    async def _rollback(self) -> None:
        await self.repository.session.rollback()
