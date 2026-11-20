import asyncio
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from api.models.chat_message import ChatMessage
from api.models.chat_session import ChatSession
from api.models.lot import Lot
from api.models.lot_draft import LotDraft
from api.models.order import Order
from api.models.order_item import OrderItem
from api.models.producer import Producer
from api.models.producer_product import ProducerProduct
from api.models.product import Product
from api.models.user import User
from api.repositories.chat import ChatRepository
from api.repositories.lot import LotRepository
from api.repositories.lot_draft import LotDraftRepository
from api.repositories.order import OrderRepository
from api.repositories.producer import ProducerRepository
from api.schemas.lot import LotCreate
from api.schemas.lot_draft import (
    LotDraftAvailabilityUpdate,
    LotDraftConfirmRequest,
    LotDraftCreate,
    LotDraftUpdate,
)
from api.schemas.order import OrderItemUpdate, OrderUpdate
from api.services.lot import LotService, LotValidationError
from api.services.lot_draft import (
    LotDraftConflictError,
    LotDraftService,
    LotDraftValidationError,
)
from api.services.order import OrderService


def _build_draft_service(session) -> LotDraftService:
    lot_service = LotService(
        repository=LotRepository(session),
        order_repository=OrderRepository(session),
        producer_repository=ProducerRepository(session),
    )
    return LotDraftService(
        draft_repository=LotDraftRepository(session),
        chat_repository=ChatRepository(session),
        order_repository=OrderRepository(session),
        lot_service=lot_service,
    )


async def _seed_order_and_user(session_maker):
    async with session_maker() as session:
        user = User(
            email=f"func-{uuid4().hex[:8]}@sabordaterra.test",
            password_hash="hashed-password",
        )
        session.add(user)
        await session.flush()

        producer = Producer(
            code=f"PR-{uuid4().hex[:8]}",
            name="Produtor Queijo Serra",
            cpf=f"{uuid4().int % 10**11:011d}",
            active=True,
        )
        product = Product(name=f"Queijo Coalho {uuid4().hex[:8]}")
        session.add_all([producer, product])
        await session.flush()

        session.add(ProducerProduct(producer_id=producer.id, product_id=product.id))
        await session.flush()

        order = Order(
            buyer="Comprador Teste #26",
            products=product.name,
            conditions="Entrega conforme cronograma",
            delivery_start_date=date(2026, 11, 4),
            delivery_end_date=date(2026, 11, 8),
            cancelled=False,
        )
        session.add(order)
        await session.flush()

        item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=Decimal("100.000"),
            unit="kg",
        )
        session.add(item)
        await session.flush()

        chat_session = await ChatRepository(session).create_session(user.id)
        await session.commit()

        return {
            "user_id": user.id,
            "producer_id": producer.id,
            "product_id": product.id,
            "order_id": order.id,
            "item_id": item.id,
            "session_id": chat_session.id,
        }


@pytest.mark.asyncio
async def test_shared_scenario_balance_change_retry_and_parallel_idempotency(
    engine: AsyncEngine,
):
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    ids = await _seed_order_and_user(session_maker)
    user_id = ids["user_id"]
    producer_id = ids["producer_id"]
    order_id = ids["order_id"]
    item_id = ids["item_id"]
    session_id = ids["session_id"]

    with pytest.raises(ValidationError):
        LotDraftAvailabilityUpdate.model_validate({"confirmed": True})
    with pytest.raises(ValidationError):
        LotDraftConfirmRequest.model_validate({})

    async with session_maker() as session:
        initial_lot = Lot(
            item_id=item_id,
            producer_id=producer_id,
            quantity=Decimal("50.000"),
            unit="kg",
            delivery_date=date(2026, 11, 5),
            availability_confirmed=True,
        )
        session.add(initial_lot)
        await session.commit()

    async with session_maker() as session:
        user = await session.get(User, user_id)
        assert user is not None
        service = _build_draft_service(session)
        _, draft = await service.create_draft_message(
            session_id,
            user,
            LotDraftCreate.model_validate(
                {
                    "pedido_id": str(order_id),
                    "item_id": str(item_id),
                    "produtor_id": str(producer_id),
                    "quantidade": "40.000",
                    "unidade": "kg",
                    "data_entrega": "2026-11-06",
                    "disponibilidade_confirmada": True,
                }
            ),
        )
        draft_id = draft.id
        assert draft.availability_confirmed is True

    async with session_maker() as session:
        lot_service = LotService(
            repository=LotRepository(session),
            order_repository=OrderRepository(session),
            producer_repository=ProducerRepository(session),
        )
        await lot_service.create(
            order_id,
            item_id,
            LotCreate(
                producer_id=producer_id,
                quantity=Decimal("25.000"),
                unit="kg",
                delivery_date=date(2026, 11, 7),
                availability_confirmed=True,
            ),
        )

    async with session_maker() as session:
        user = await session.get(User, user_id)
        assert user is not None
        service = _build_draft_service(session)
        current_draft = await LotDraftRepository(session).get_by_id(draft_id)
        assert current_draft is not None

        with pytest.raises(LotValidationError) as exc_info:
            await service.confirm_draft(
                draft_id,
                user,
                LotDraftConfirmRequest(expected_revision=current_draft.revision),
            )

        assert "25" in str(exc_info.value)

    async with session_maker() as session:
        preserved = await LotDraftRepository(session).get_by_id(draft_id)
        assert preserved is not None
        assert preserved.lot_id is None
        assert preserved.quantity == Decimal("40.000")
        assert preserved.delivery_date == date(2026, 11, 6)

    async with session_maker() as session:
        user = await session.get(User, user_id)
        assert user is not None
        service = _build_draft_service(session)
        with pytest.raises(LotDraftConflictError):
            await service.set_availability(
                draft_id,
                user,
                LotDraftAvailabilityUpdate(confirmed=True, expected_revision=999),
            )
        with pytest.raises(LotDraftConflictError):
            await service.confirm_draft(
                draft_id,
                user,
                LotDraftConfirmRequest(expected_revision=999),
            )

    async with session_maker() as session:
        user = await session.get(User, user_id)
        assert user is not None
        service = _build_draft_service(session)

        updated = await service.update_draft(
            draft_id,
            user,
            LotDraftUpdate(quantity=Decimal("5.000")),
        )
        assert updated.availability_confirmed is False

        avail = await service.set_availability(
            draft_id,
            user,
            LotDraftAvailabilityUpdate(
                confirmed=True,
                expected_revision=updated.revision,
            ),
        )
        assert avail.availability_confirmed is True
        confirmed_revision = avail.revision

    async def run_confirm_attempt():
        async with session_maker() as session:
            user = await session.get(User, user_id)
            assert user is not None
            service = _build_draft_service(session)
            return await service.confirm_draft(
                draft_id,
                user,
                LotDraftConfirmRequest(expected_revision=confirmed_revision),
            )

    results = await asyncio.gather(run_confirm_attempt(), run_confirm_attempt())
    assert results[0].lot_id is not None
    assert results[0].lot_id == results[1].lot_id

    async with session_maker() as session:
        lots = list(
            (
                await session.scalars(
                    select(Lot).where(
                        Lot.item_id == item_id,
                        Lot.delivery_date == date(2026, 11, 6),
                    )
                )
            ).all()
        )
        assert len(lots) == 1
        assert lots[0].quantity == Decimal("5.000")

        await session.execute(delete(Lot).where(Lot.id == results[0].lot_id))
        await session.commit()

    async with session_maker() as session:
        user = await session.get(User, user_id)
        assert user is not None
        service = _build_draft_service(session)
        after_delete = await LotDraftRepository(session).get_by_id(draft_id)
        assert after_delete is not None
        assert after_delete.lot_id is None
        assert after_delete.status == "confirmado"

        with pytest.raises(LotDraftConflictError):
            await service.confirm_draft(
                draft_id,
                user,
                LotDraftConfirmRequest(expected_revision=after_delete.revision),
            )


@pytest.mark.asyncio
async def test_blocks_confirm_when_needs_date_review_and_allows_item_deletion_with_only_draft(
    engine: AsyncEngine,
):
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    ids = await _seed_order_and_user(session_maker)
    user_id = ids["user_id"]
    producer_id = ids["producer_id"]
    product_id = ids["product_id"]
    order_id = ids["order_id"]
    item_id = ids["item_id"]
    session_id = ids["session_id"]

    async with session_maker() as session:
        user = await session.get(User, user_id)
        assert user is not None
        service = _build_draft_service(session)
        _, draft = await service.create_draft_message(
            session_id,
            user,
            LotDraftCreate.model_validate(
                {
                    "pedido_id": str(order_id),
                    "item_id": str(item_id),
                    "produtor_id": str(producer_id),
                    "quantidade": "10.000",
                    "unidade": "kg",
                    "data_entrega": "2026-11-06",
                    "disponibilidade_confirmada": True,
                }
            ),
        )
        draft_id = draft.id

        draft_row = await session.get(LotDraft, draft_id)
        assert draft_row is not None
        draft_row.needs_date_review = True
        draft_row.revision += 1
        await session.commit()
        rev_with_review = draft_row.revision

    async with session_maker() as session:
        user = await session.get(User, user_id)
        assert user is not None
        service = _build_draft_service(session)
        with pytest.raises(LotDraftValidationError):
            await service.confirm_draft(
                draft_id,
                user,
                LotDraftConfirmRequest(expected_revision=rev_with_review),
            )

    async with session_maker() as session:
        order = await OrderRepository(session).get_by_id(order_id)
        assert order is not None
        replacement_product = Product(name=f"Outro Produto {uuid4().hex[:8]}")
        session.add(replacement_product)
        await session.flush()

        order_service = OrderService(
            repository=OrderRepository(session),
            product_repository=ProductRepository(session)
            if "ProductRepository" in globals()
            else __import__(
                "api.repositories.product", fromlist=["ProductRepository"]
            ).ProductRepository(session),
        )
        await order_service.update_order(
            order_id,
            OrderUpdate(
                version=order.version,
                buyer=order.buyer,
                conditions=order.conditions,
                delivery_start_date=order.delivery_start_date,
                delivery_end_date=order.delivery_end_date,
                items=[
                    OrderItemUpdate(
                        id=None,
                        product_id=replacement_product.id,
                        quantity=Decimal("15.000"),
                        unit="kg",
                    )
                ],
            ),
        )

    async with session_maker() as session:
        deleted_item = await session.get(OrderItem, item_id)
        assert deleted_item is None
        updated_draft = await LotDraftRepository(session).get_by_id(draft_id)
        assert updated_draft is not None
        assert updated_draft.item_id is None
        assert updated_draft.order_id == order_id
        assert updated_draft.producer_id == producer_id
        assert updated_draft.quantity == Decimal("10.000")
        assert product_id is not None


@pytest.mark.asyncio
async def test_concurrent_confirm_draft_and_item_removal_do_not_deadlock(
    engine: AsyncEngine,
):
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    ids = await _seed_order_and_user(session_maker)
    user_id = ids["user_id"]
    producer_id = ids["producer_id"]
    order_id = ids["order_id"]
    item_id = ids["item_id"]
    session_id = ids["session_id"]

    async with session_maker() as session:
        user = await session.get(User, user_id)
        assert user is not None
        service = _build_draft_service(session)
        _, draft = await service.create_draft_message(
            session_id,
            user,
            LotDraftCreate.model_validate(
                {
                    "pedido_id": str(order_id),
                    "item_id": str(item_id),
                    "produtor_id": str(producer_id),
                    "quantidade": "10.000",
                    "unidade": "kg",
                    "data_entrega": "2026-11-06",
                    "disponibilidade_confirmada": True,
                }
            ),
        )
        draft_id = draft.id
        revision = draft.revision

    async def confirm_worker():
        async with session_maker() as session:
            user = await session.get(User, user_id)
            assert user is not None
            service = _build_draft_service(session)
            try:
                return await service.confirm_draft(
                    draft_id,
                    user,
                    LotDraftConfirmRequest(expected_revision=revision),
                )
            except Exception as exc:  # noqa: BLE001
                return exc

    async def remove_item_worker():
        async with session_maker() as session:
            from api.repositories.product import ProductRepository

            order = await OrderRepository(session).get_by_id(order_id)
            assert order is not None
            replacement_product = Product(name=f"Item Substituto {uuid4().hex[:8]}")
            session.add(replacement_product)
            await session.flush()

            order_service = OrderService(
                repository=OrderRepository(session),
                product_repository=ProductRepository(session),
            )
            try:
                return await order_service.update_order(
                    order_id,
                    OrderUpdate(
                        version=order.version,
                        buyer=order.buyer,
                        conditions=order.conditions,
                        delivery_start_date=order.delivery_start_date,
                        delivery_end_date=order.delivery_end_date,
                        items=[
                            OrderItemUpdate(
                                id=None,
                                product_id=replacement_product.id,
                                quantity=Decimal("10.000"),
                                unit="kg",
                            )
                        ],
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                return exc

    res_confirm, res_remove = await asyncio.gather(
        confirm_worker(),
        remove_item_worker(),
    )
    assert res_confirm is not None
    assert res_remove is not None

    async with session_maker() as session:
        final_draft = await LotDraftRepository(session).get_by_id(draft_id)
        assert final_draft is not None
        if final_draft.lot_id is not None:
            deleted_item = await session.get(OrderItem, item_id)
            assert deleted_item is not None
        else:
            deleted_item = await session.get(OrderItem, item_id)
            assert deleted_item is None
            assert final_draft.item_id is None
