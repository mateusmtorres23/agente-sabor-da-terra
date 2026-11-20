from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import (
    ChatSession,
    Order,
    OrderDraft,
    OrderItem,
    Product,
    User,
)
from api.repositories.order import OrderRepository
from api.repositories.product import ProductRepository
from api.schemas.order import OrderCreate
from api.schemas.order_draft import OrderDraftData
from api.services.order import OrderService

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def context(
    db_session: AsyncSession,
) -> tuple[OrderService, UUID, UUID]:
    user = User(
        email=f"{uuid4()}@example.com",
        password_hash="unused",
    )
    product = Product(name=f"Queijo coalho {uuid4()}")

    db_session.add_all([user, product])
    await db_session.flush()

    chat = ChatSession(
        user_id=user.id,
        title="Confirmação de pedido",
    )
    db_session.add(chat)
    await db_session.commit()

    service = OrderService(
        OrderRepository(db_session),
        ProductRepository(db_session),
    )

    return service, chat.id, product.id


def order_payload(product_id: UUID) -> OrderCreate:
    return OrderCreate.model_validate(
        {
            "buyer": "Mercado Bom Preço",
            "conditions": "Entrega pela manhã",
            "delivery_start_date": "2026-11-06",
            "items": [
                {
                    "product_id": str(product_id),
                    "quantity": "10.125",
                    "unit": "kg",
                }
            ],
        }
    )


async def test_order_and_confirmation_can_be_committed_together(
    db_session: AsyncSession,
    context: tuple[OrderService, UUID, UUID],
) -> None:
    service, session_id, product_id = context
    payload = order_payload(product_id)

    order = await service.create_order(
        payload,
        session_id=session_id,
        commit=False,
    )

    assert order.id is not None
    assert order.items[0].id is not None

    reviewed = payload.model_dump(mode="json")

    draft = OrderDraft(
        session_id=session_id,
        data=OrderDraftData.model_validate(reviewed).model_dump(
            mode="json"
        ),
        confirmed_order_id=order.id,
        confirmation_payload=reviewed,
    )
    db_session.add(draft)

    await db_session.commit()

    order_id = order.id
    draft_id = draft.id
    item_id = order.items[0].id

    db_session.expunge_all()

    saved_order = await service.repository.get_by_session(
        session_id
    )
    saved_draft = await db_session.get(OrderDraft, draft_id)

    assert saved_order is not None
    assert saved_order.id == order_id
    assert saved_order.session_id == session_id
    assert saved_order.items[0].id == item_id

    assert saved_draft is not None
    assert saved_draft.confirmed_order_id == order_id
    assert saved_draft.confirmation_payload == reviewed

    assert await service.repository.get_by_session(uuid4()) is None


async def test_confirmation_failure_rolls_back_order_and_items(
    db_session: AsyncSession,
    context: tuple[OrderService, UUID, UUID],
) -> None:
    service, session_id, product_id = context
    payload = order_payload(product_id)

    order = await service.create_order(
        payload,
        session_id=session_id,
        commit=False,
    )
    order_id = order.id
    draft_id = uuid4()

    db_session.add(
        OrderDraft(
            id=draft_id,
            session_id=session_id,
            data=OrderDraftData().model_dump(mode="json"),
            confirmed_order_id=order_id,
            confirmation_payload=None,
        )
    )

    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()

    assert await db_session.get(Order, order_id) is None
    assert await db_session.get(OrderDraft, draft_id) is None

    item_count = await db_session.scalar(
        select(func.count())
        .select_from(OrderItem)
        .where(OrderItem.order_id == order_id)
    )
    assert item_count == 0