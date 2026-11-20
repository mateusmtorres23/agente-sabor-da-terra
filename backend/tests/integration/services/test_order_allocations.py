from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Lot, Producer, ProducerProduct, Product
from api.repositories.lot import LotRepository
from api.repositories.order import OrderRepository
from api.repositories.producer import ProducerRepository
from api.repositories.product import ProductRepository
from api.schemas.lot import LotCreate
from api.schemas.order import OrderCreate, OrderUpdate
from api.services.lot import LotConflictError, LotService
from api.services.order import OrderService, OrderValidationError

pytestmark = pytest.mark.asyncio


def order_service(db_session: AsyncSession) -> OrderService:
    return OrderService(OrderRepository(db_session), ProductRepository(db_session))


def lot_service(db_session: AsyncSession) -> LotService:
    return LotService(
        LotRepository(db_session),
        OrderRepository(db_session),
        ProducerRepository(db_session),
    )


@pytest_asyncio.fixture
async def setup_order(db_session: AsyncSession) -> SimpleNamespace:
    product = Product(name="Tomate")
    producer = Producer(code="P001", name="Ana Silva", cpf="01234567890", active=True)
    db_session.add_all([product, producer])
    await db_session.flush()
    db_session.add(ProducerProduct(producer_id=producer.id, product_id=product.id))

    order = await order_service(db_session).create_order(
        OrderCreate.model_validate(
            {
                "buyer": "Mercado",
                "conditions": "",
                "delivery_start_date": "2026-11-04",
                "delivery_end_date": "2026-11-08",
                "items": [
                    {
                        "product_id": str(product.id),
                        "quantity": "100",
                        "unit": "kg",
                    }
                ],
            }
        )
    )
    item = order.items[0]

    lot = await lot_service(db_session).create(
        order.id,
        item.id,
        LotCreate.model_validate(
            {
                "producer_id": str(producer.id),
                "quantity": "50",
                "unit": "kg",
                "delivery_date": "2026-11-04",
                "availability_confirmed": True,
            }
        ),
    )

    return SimpleNamespace(product=product, producer=producer, order=order, item=item, lot=lot)


def update_payload(
    item_id: UUID,
    product_id: UUID,
    *,
    quantity: str = "100",
    unit: str = "kg",
    delivery_start: str = "2026-11-04",
    delivery_end: str | None = "2026-11-08",
    version: int = 1,
) -> OrderUpdate:
    return OrderUpdate.model_validate(
        {
            "buyer": "Mercado",
            "version": version,
            "conditions": "",
            "delivery_start_date": delivery_start,
            "delivery_end_date": delivery_end,
            "items": [
                {
                    "id": str(item_id),
                    "product_id": str(product_id),
                    "quantity": quantity,
                    "unit": unit,
                }
            ],
        }
    )


async def test_update_rejects_delivery_date_outside_allocations(
    db_session: AsyncSession,
    setup_order: SimpleNamespace,
) -> None:
    payload = update_payload(
        setup_order.item.id,
        setup_order.product.id,
        delivery_start="2026-11-05",
        delivery_end="2026-11-08",
    )

    with pytest.raises(OrderValidationError, match="alocação"):
        await order_service(db_session).update_order(setup_order.order.id, payload)


async def test_update_rejects_removing_item_with_allocations(
    db_session: AsyncSession,
    setup_order: SimpleNamespace,
) -> None:
    payload = OrderUpdate.model_validate(
        {
            "buyer": "Mercado",
            "version": 1,
            "conditions": "",
            "delivery_start_date": "2026-11-04",
            "delivery_end_date": "2026-11-08",
            "items": [
                {
                    "product_id": str(setup_order.product.id),
                    "quantity": "100",
                    "unit": "kg",
                }
            ],
        }
    )

    with pytest.raises(OrderValidationError, match="remover"):
        await order_service(db_session).update_order(setup_order.order.id, payload)


async def test_update_rejects_quantity_below_allocated(
    db_session: AsyncSession,
    setup_order: SimpleNamespace,
) -> None:
    payload = update_payload(
        setup_order.item.id,
        setup_order.product.id,
        quantity="40",
    )

    with pytest.raises(OrderValidationError, match="alocado"):
        await order_service(db_session).update_order(setup_order.order.id, payload)


async def test_update_allows_quantity_equal_to_allocated(
    db_session: AsyncSession,
    setup_order: SimpleNamespace,
) -> None:
    payload = update_payload(
        setup_order.item.id,
        setup_order.product.id,
        quantity="50",
    )
    updated = await order_service(db_session).update_order(setup_order.order.id, payload)
    assert updated.items[0].quantity == Decimal(50)


async def test_cancel_removes_operational_lots_and_preserves_imported(
    db_session: AsyncSession,
    setup_order: SimpleNamespace,
) -> None:
    imported = Lot(
        item_id=None,
        producer_id=setup_order.producer.id,
        quantity=Decimal(300),
        unit=None,
        delivery_date=date(2026, 9, 8),
    )
    db_session.add(imported)
    await db_session.commit()

    await order_service(db_session).cancel_order(setup_order.order.id)
    db_session.expire_all()

    lots = list(await db_session.scalars(select(Lot)))
    imported_db = await db_session.get(Lot, imported.id)
    deleted_lot_db = await db_session.get(Lot, setup_order.lot.id)
    assert imported_db is not None
    assert imported_db.item_id is None
    assert deleted_lot_db is None
    assert all(lot.item_id is None for lot in lots if lot.id in {imported.id, setup_order.lot.id})


async def test_cancelled_order_rejects_lot_save(
    db_session: AsyncSession,
    setup_order: SimpleNamespace,
) -> None:
    await order_service(db_session).cancel_order(setup_order.order.id)

    with pytest.raises(LotConflictError):
        await lot_service(db_session).create(
            setup_order.order.id,
            setup_order.item.id,
            LotCreate.model_validate(
                {
                    "producer_id": str(setup_order.producer.id),
                    "quantity": "10",
                    "unit": "kg",
                    "delivery_date": "2026-11-04",
                    "availability_confirmed": True,
                }
            ),
        )
