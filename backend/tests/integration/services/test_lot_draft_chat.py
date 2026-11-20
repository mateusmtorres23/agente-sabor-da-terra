import asyncio
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from api.database import get_session_maker
from api.models.lot import Lot
from api.models.order import Order
from api.models.order_item import OrderItem
from api.models.producer import Producer
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
    LotDraftCreate,
    LotDraftUpdate,
)
from api.services.lot import LotService, LotValidationError
from api.services.lot_draft import LotDraftService


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
async def test_shared_scenario_balance_change_retry_and_parallel_idempotency():
    session_maker = get_session_maker()

    # 1. Prepara usuário, sessão, produtor ativo, produto e pedido com 100 kg e 50 kg já alocados
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

        # Associa produtor ao produto na tabela producer_products se necessário
        from api.models.producer_product import ProducerProduct

        session.add(ProducerProduct(producer_id=producer.id, product_id=product.id))

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

        # Alocação inicial de 50 kg -> saldo inicial de 50 kg
        initial_lot = Lot(
            item_id=item.id,
            producer_id=producer.id,
            quantity=Decimal("50.000"),
            unit="kg",
            delivery_date=date(2026, 11, 5),
            availability_confirmed=True,
        )
        session.add(initial_lot)
        await session.commit()

        order_id = order.id
        item_id = item.id
        producer_id = producer.id
        user_id = user.id

    # Cria sessão e rascunho no formato da #26 (40 kg para 06/11, disponibilidade confirmada)
    async with session_maker() as session:
        user = await session.get(User, user_id)
        assert user is not None
        chat_session = await ChatRepository(session).create_session(user.id)
        await session.commit()
        session_id = chat_session.id

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

    # Passo 1: Outra operação aloca 25 kg antes da autorização -> saldo cai para 25 kg
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

    # Passo 2: Funcionário tenta cadastrar os 40 kg -> rejeita, informa 25 kg e preserva rascunho
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

    # Passo 3: Muda quantidade para 20 kg (invalida disponibilidade), confirma disponibilidade e autoriza
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
            LotDraftAvailabilityUpdate(confirmed=True),
        )
        assert avail.availability_confirmed is True

    # Passo 4: Confirmações em paralelo geram um único lote de 20 kg para 06/11
    async def run_confirm_attempt():
        async with session_maker() as session:
            user = await session.get(User, user_id)
            assert user is not None
            service = _build_draft_service(session)
            return await service.confirm_draft(draft_id, user)

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
        assert lots[0].quantity == Decimal("20.000")