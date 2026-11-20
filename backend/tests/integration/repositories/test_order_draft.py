from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import (
    ChatSession,
    Order,
    OrderDraft,
    OrderItem,
    Product,
    User,
)
from api.repositories.order_draft import OrderDraftRepository
from api.schemas.order_draft import OrderDraftData

pytestmark = pytest.mark.asyncio


@pytest.fixture
def repository(db_session: AsyncSession) -> OrderDraftRepository:
    return OrderDraftRepository(db_session)


@pytest_asyncio.fixture
async def session_ids(
    db_session: AsyncSession,
) -> tuple[UUID, UUID]:
    user = User(
        email=f"{uuid4()}@example.com",
        password_hash="unused",
    )
    db_session.add(user)
    await db_session.flush()

    first = ChatSession(
        user_id=user.id,
        title="Primeira conversa",
    )
    second = ChatSession(
        user_id=user.id,
        title="Segunda conversa",
    )
    db_session.add_all([first, second])
    await db_session.commit()

    return first.id, second.id


def draft_data(buyer: str) -> dict:
    return OrderDraftData(
        buyer=buyer,
        pending=["Completar os dados do pedido."],
    ).model_dump(mode="json")


async def test_add_persists_draft_and_preserves_json(
    repository: OrderDraftRepository,
    db_session: AsyncSession,
    session_ids: tuple[UUID, UUID],
) -> None:
    first, _ = session_ids
    data = draft_data("Mercado Central")

    draft = OrderDraft(
        session_id=first,
        data=data,
        confirmation_payload=None,
    )
    repository.add(draft)
    await db_session.commit()

    draft_id = draft.id

    # Remove os objetos da memória para consultar novamente o banco.
    db_session.expunge_all()

    saved = await repository.get_by_id(
        draft_id,
        session_id=first,
    )

    assert saved is not None
    assert saved.id == draft_id
    assert saved.session_id == first
    assert saved.version == 1
    assert saved.data == data
    assert saved.confirmed_order_id is None
    assert saved.confirmation_payload is None
    assert saved.created_at is not None


@pytest.mark.parametrize("lock", [False, True])
async def test_get_by_id_does_not_return_another_sessions_draft(
    repository: OrderDraftRepository,
    db_session: AsyncSession,
    session_ids: tuple[UUID, UUID],
    lock: bool,
) -> None:
    first, second = session_ids

    draft = OrderDraft(
        session_id=first,
        data=draft_data("Primeira conversa"),
    )
    repository.add(draft)
    await db_session.commit()

    hidden = await repository.get_by_id(
        draft.id,
        session_id=second,
        lock=lock,
    )

    assert hidden is None

    missing = await repository.get_by_id(
        uuid4(),
        session_id=first,
        lock=lock,
    )

    assert missing is None


async def test_latest_draft_is_selected_within_its_session(
    repository: OrderDraftRepository,
    db_session: AsyncSession,
    session_ids: tuple[UUID, UUID],
) -> None:
    first, second = session_ids
    base_time = datetime(2026, 11, 6, tzinfo=UTC)

    older = OrderDraft(
        session_id=first,
        data=draft_data("Antigo"),
        created_at=base_time,
    )
    latest = OrderDraft(
        session_id=first,
        data=draft_data("Mais recente da primeira conversa"),
        created_at=base_time + timedelta(minutes=1),
    )

    repository.add(older)
    repository.add(latest)
    await db_session.commit()

    assert await repository.get_latest_for_session(second) is None

    other = OrderDraft(
        session_id=second,
        data=draft_data("Outra conversa"),
        created_at=base_time + timedelta(minutes=2),
    )
    repository.add(other)
    await db_session.commit()

    saved = await repository.get_latest_for_session(first)

    assert saved is not None
    assert saved.id == latest.id
    assert saved.data["buyer"] == (
        "Mais recente da primeira conversa"
    )

    saved_other = await repository.get_latest_for_session(second)

    assert saved_other is not None
    assert saved_other.id == other.id


async def test_confirmed_draft_is_found_even_after_order_cancellation(
    repository: OrderDraftRepository,
    db_session: AsyncSession,
    session_ids: tuple[UUID, UUID],
) -> None:
    first, second = session_ids
    product = Product(name=f"Queijo coalho {uuid4()}")

    db_session.add(product)
    await db_session.flush()

    reviewed = {
        "buyer": "Comprador revisado",
        "conditions": "Entrega pela manhã",
        "delivery_start_date": "2026-11-06",
        "delivery_end_date": None,
        "items": [
            {
                "product_id": str(product.id),
                "quantity": "10",
                "unit": "kg",
            }
        ],
    }

    order = Order(
        session_id=first,
        buyer=reviewed["buyer"],
        products="",
        conditions=reviewed["conditions"],
        delivery_start_date=date(2026, 11, 6),
        items=[
            OrderItem(
                product_id=product.id,
                product=product,
                quantity=Decimal(10),
                unit="kg",
            )
        ],
    )
    db_session.add(order)
    await db_session.flush()

    base_time = datetime(2026, 11, 6, tzinfo=UTC)

    confirmed = OrderDraft(
        session_id=first,
        data=OrderDraftData.model_validate(reviewed).model_dump(
            mode="json"
        ),
        confirmed_order_id=order.id,
        confirmation_payload=reviewed,
        created_at=base_time,
    )
    newer_pending = OrderDraft(
        session_id=first,
        data=draft_data("Ainda não confirmado"),
        created_at=base_time + timedelta(minutes=1),
    )
    other_pending = OrderDraft(
        session_id=second,
        data=draft_data("Segunda conversa"),
    )

    repository.add(confirmed)
    repository.add(newer_pending)
    repository.add(other_pending)
    await db_session.commit()

    saved = await repository.get_confirmed_for_session(first)

    assert saved is not None
    assert saved.id == confirmed.id
    assert saved.confirmed_order_id == order.id
    assert saved.confirmation_payload == reviewed
    assert await repository.get_confirmed_for_session(second) is None

    order.cancelled = True
    order.version += 1
    await db_session.commit()

    db_session.expunge_all()

    preserved = await repository.get_confirmed_for_session(first)

    assert preserved is not None
    assert preserved.id == saved.id
    assert preserved.confirmed_order_id == saved.confirmed_order_id
    assert preserved.confirmation_payload == reviewed


async def test_repository_add_does_not_commit_the_transaction(
    repository: OrderDraftRepository,
    db_session: AsyncSession,
    session_ids: tuple[UUID, UUID],
) -> None:
    first, _ = session_ids

    draft = OrderDraft(
        session_id=first,
        data=draft_data("Não deve permanecer salvo"),
    )
    repository.add(draft)
    await db_session.flush()

    draft_id = draft.id

    assert await repository.get_by_id(
        draft_id,
        session_id=first,
    ) is not None

    await db_session.rollback()

    assert await repository.get_by_id(
        draft_id,
        session_id=first,
    ) is None