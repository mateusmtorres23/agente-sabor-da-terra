import asyncio
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from api.models import Base
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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
from api.services.lot import LotService, LotValidationError
from api.services.lot_draft import LotDraftConflictError, LotDraftService


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


@pytest.mark.asyncio
async def test_shared_scenario_balance_change_retry_and_parallel_idempotency(
    database_url: str,
):
    isolated_engine = create_async_engine(database_url)
    async with isolated_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(isolated_engine, expire_on_commit=False)

    created_ids: dict[str, list[UUID]] = {
        "lots": [],
        "drafts": [],
        "messages": [],
        "sessions": [],
        "items": [],
        "orders": [],
        "producer_products": [],
        "producers": [],
        "products": [],
        "users": [],
    }

    try:
        async with session_maker() as session:
            user = User(
                email=f"func-{uuid4().hex[:8]}@sabordaterra.test",
                password_hash="hashed-password",
            )
            session.add(user)
            await session.flush()
            created_ids["users"].append(user.id)

            producer = Producer(
                code=f"PR-{uuid4().hex[:8]}",
                name="Produtor Queijo Serra",
                cpf=f"{uuid4().int % 10**11:011d}",
                active=True,
            )
            product = Product(name=f"Queijo Coalho {uuid4().hex[:8]}")
            session.add_all([producer, product])
            await session.flush()
            created_ids["producers"].append(producer.id)
            created_ids["products"].append(product.id)

            pp = ProducerProduct(producer_id=producer.id, product_id=product.id)
            session.add(pp)
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
            created_ids["orders"].append(order.id)

            item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=Decimal("100.000"),
                unit="kg",
            )
            session.add(item)
            await session.flush()
            created_ids["items"].append(item.id)

            initial_lot = Lot(
                item_id=item.id,
                producer_id=producer.id,
                quantity=Decimal("50.000"),
                unit="kg",
                delivery_date=date(2026, 11, 5),
                availability_confirmed=True,
            )
            session.add(initial_lot)
            await session.flush()
            created_ids["lots"].append(initial_lot.id)
            await session.commit()

            order_id = order.id
            item_id = item.id
            producer_id = producer.id
            user_id = user.id

        async with session_maker() as session:
            user = await session.get(User, user_id)
            assert user is not None
            chat_session = await ChatRepository(session).create_session(user.id)
            await session.commit()
            session_id = chat_session.id
            created_ids["sessions"].append(session_id)

        async with session_maker() as session:
            user = await session.get(User, user_id)
            assert user is not None
            service = _build_draft_service(session)
            message, draft = await service.create_draft_message(
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
            created_ids["drafts"].append(draft_id)
            created_ids["messages"].append(message.id)
            assert draft.availability_confirmed is True

        # Outra operação aloca 25 kg antes da autorização -> saldo cai para 25 kg
        async with session_maker() as session:
            lot_service = LotService(
                repository=LotRepository(session),
                order_repository=OrderRepository(session),
                producer_repository=ProducerRepository(session),
            )
            extra_lot = await lot_service.create(
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
            created_ids["lots"].append(extra_lot.id)

        # Rejeita os 40 kg, informa saldo de 25 kg e preserva rascunho
        async with session_maker() as session:
            user = await session.get(User, user_id)
            assert user is not None
            service = _build_draft_service(session)

            with pytest.raises(LotValidationError) as exc_info:
                await service.confirm_draft(draft_id, user)

            assert "25" in str(exc_info.value)

        async with session_maker() as session:
            preserved = await LotDraftRepository(session).get_by_id(draft_id)
            assert preserved is not None
            assert preserved.lot_id is None
            assert preserved.quantity == Decimal("40.000")
            assert preserved.delivery_date == date(2026, 11, 6)

        # Revisão stale (expected_revision desatualizada) gera conflito
        async with session_maker() as session:
            user = await session.get(User, user_id)
            assert user is not None
            service = _build_draft_service(session)
            with pytest.raises(LotDraftConflictError):
                await service.confirm_draft(
                    draft_id,
                    user,
                    LotDraftConfirmRequest(expected_revision=999),
                )

        # Atualiza quantidade para 20 kg (invalida disponibilidade), reconfirma e autoriza
        async with session_maker() as session:
            user = await session.get(User, user_id)
            assert user is not None
            service = _build_draft_service(session)

            updated = await service.update_draft(
                draft_id,
                user,
                LotDraftUpdate(quantity=Decimal("20.000")),
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

        # Confirmações em paralelo com conexões independentes geram um único lote
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
        created_ids["lots"].append(results[0].lot_id)

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
            assert lots[0].quantity == Decimal("20.000")

            # Se o lote confirmado for excluído, o rascunho não volta para revisão nem recria o lote
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
                await service.confirm_draft(draft_id, user)
    finally:
        async with session_maker() as cleanup:
            if created_ids["drafts"]:
                await cleanup.execute(
                    delete(LotDraft).where(LotDraft.id.in_(created_ids["drafts"]))
                )
            if created_ids["producers"] and created_ids["products"]:
                await cleanup.execute(
                    delete(ProducerProduct).where(
                        ProducerProduct.producer_id.in_(created_ids["producers"]),
                        ProducerProduct.product_id.in_(created_ids["products"]),
                    )
                )
            if created_ids["messages"]:
                await cleanup.execute(
                    delete(ChatMessage).where(
                        ChatMessage.id.in_(created_ids["messages"])
                    )
                )
            if created_ids["sessions"]:
                await cleanup.execute(
                    delete(ChatSession).where(
                        ChatSession.id.in_(created_ids["sessions"])
                    )
                )
            if created_ids["lots"]:
                await cleanup.execute(
                    delete(Lot).where(Lot.id.in_(created_ids["lots"]))
                )
            if created_ids["items"]:
                await cleanup.execute(
                    delete(OrderItem).where(
                        OrderItem.id.in_(created_ids["items"])
                    )
                )
            if created_ids["orders"]:
                await cleanup.execute(
                    delete(Order).where(Order.id.in_(created_ids["orders"]))
                )
            if created_ids["producer_products"]:
                await cleanup.execute(
                    delete(ProducerProduct).where(
                        ProducerProduct.id.in_(created_ids["producer_products"])
                    )
                )
            if created_ids["producers"]:
                await cleanup.execute(
                    delete(Producer).where(
                        Producer.id.in_(created_ids["producers"])
                    )
                )
            if created_ids["products"]:
                await cleanup.execute(
                    delete(Product).where(
                        Product.id.in_(created_ids["products"])
                    )
                )
            if created_ids["users"]:
                await cleanup.execute(
                    delete(User).where(User.id.in_(created_ids["users"]))
                )
            await cleanup.commit()

        await isolated_engine.dispose()