from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Lot, Order, OrderItem, Producer, ProducerProduct, Product
from api.repositories.lot import LotRepository
from api.repositories.order import OrderRepository
from api.repositories.producer import ProducerRepository
from api.schemas.lot import LotCreate
from api.services.lot import LotService
from tests.integration.routers.test_chat import (  # noqa: F401
    client,
    create_user_headers,
)

pytestmark = pytest.mark.asyncio

FAKE_ID = uuid4()


async def seed_catalog(session: AsyncSession) -> SimpleNamespace:
    """Item de 100 kg, 50 kg já alocados (saldo 50 kg), prazo de 4 a 8/11."""
    suffix = uuid4().hex[:8]
    product = Product(name=f"Queijo coalho {suffix}")
    producer = Producer(
        code=f"A{suffix}", name="Ana Silva", cpf=uuid4().hex[:11], active=True
    )
    session.add_all([product, producer])
    await session.flush()
    session.add(ProducerProduct(producer_id=producer.id, product_id=product.id))
    order = Order(
        buyer="Mercado Bom Preço",
        products="",
        conditions="",
        delivery_start_date=date(2026, 11, 4),
        delivery_end_date=date(2026, 11, 8),
    )
    session.add(order)
    await session.flush()
    item = OrderItem(
        order_id=order.id, product_id=product.id, quantity=Decimal(100), unit="kg"
    )
    session.add(item)
    await session.flush()
    session.add(
        Lot(
            item_id=item.id,
            producer_id=producer.id,
            quantity=Decimal(50),
            unit="kg",
            delivery_date=date(2026, 11, 5),
            availability_confirmed=True,
        )
    )
    env = SimpleNamespace(
        order_id=order.id, item_id=item.id, producer_id=producer.id
    )
    await session.commit()
    return env


def draft_body(env: SimpleNamespace, **overrides) -> dict:
    return {
        "order_id": str(env.order_id),
        "item_id": str(env.item_id),
        "producer_id": str(env.producer_id),
        "quantity": "40",
        "unit": "kg",
        "delivery_date": "2026-11-06",
        "availability_confirmed": True,
        **overrides,
    }


async def new_session(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    created = await client.post("/chat/sessions", headers=headers)
    assert created.status_code == 201
    return created.json()["id"]


async def create_draft(
    client: httpx.AsyncClient, headers: dict[str, str], session_id: str, body: dict
) -> dict:
    response = await client.post(
        f"/chat/sessions/{session_id}/lot-drafts", headers=headers, json=body
    )
    assert response.status_code == 201, response.text
    message = response.json()
    assert message.get("lot_draft"), "MessageOut precisa expor lot_draft"
    return message["lot_draft"]


async def draft_from_chat(
    client: httpx.AsyncClient, headers: dict[str, str], session_id: str
) -> dict:
    response = await client.get(f"/chat/sessions/{session_id}", headers=headers)
    assert response.status_code == 200
    [message] = [m for m in response.json()["messages"] if m.get("lot_draft")]
    return message["lot_draft"]


def lot_service(session: AsyncSession) -> LotService:
    return LotService(
        LotRepository(session),
        OrderRepository(session),
        ProducerRepository(session),
    )


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", f"/chat/sessions/{FAKE_ID}/lot-drafts"),
        ("PATCH", f"/chat/lot-drafts/{FAKE_ID}"),
        ("POST", f"/chat/lot-drafts/{FAKE_ID}/availability"),
        ("POST", f"/chat/lot-drafts/{FAKE_ID}/confirm"),
    ],
)
async def test_draft_routes_require_a_valid_jwt(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    missing = await client.request(method, path, json={})
    invalid = await client.request(
        method, path, json={}, headers={"Authorization": "Bearer token-invalido"}
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401


async def test_shared_scenario_through_the_api(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    env = await seed_catalog(db_session)
    headers = await create_user_headers(db_session)
    session_id = await new_session(client, headers)

    # O chat mostra o rascunho com o prazo do pedido separado da data do lote.
    draft = await create_draft(client, headers, session_id, draft_body(env))
    draft_id = draft["id"]
    assert draft["status"] == "em_revisao"
    assert draft["delivery_date"] == "2026-11-06"
    assert draft["order_deadline"]["delivery_start_date"] == "2026-11-04"
    assert draft["order_deadline"]["delivery_end_date"] == "2026-11-08"

    # Antes da autorização, outra operação aloca 25 kg (saldo cai para 25 kg).
    await lot_service(db_session).create(
        env.order_id,
        env.item_id,
        LotCreate.model_validate(
            {
                "producer_id": str(env.producer_id),
                "quantity": "25",
                "unit": "kg",
                "delivery_date": "2026-11-05",
                "availability_confirmed": True,
            }
        ),
    )

    # Os 40 kg são rejeitados, o motivo informa o saldo e o rascunho é preservado.
    rejected = await client.post(f"/chat/lot-drafts/{draft_id}/confirm", headers=headers, json={"expected_revision": draft["revision"]})
    assert rejected.status_code == 422
    assert "saldo atual: 25 kg" in rejected.json()["detail"]
    preserved = await draft_from_chat(client, headers, session_id)
    assert preserved["status"] == "em_revisao"
    assert Decimal(str(preserved["quantity"])) == Decimal(40)
    assert preserved["saved_lot"] is None

    # Revisa para 20 kg: a disponibilidade volta a ficar pendente.
    patched = await client.patch(
        f"/chat/lot-drafts/{draft_id}", headers=headers, json={"quantity": "20"}
    )
    assert patched.status_code == 200
    assert patched.json()["availability_confirmed"] is False

    # Confirmar a disponibilidade só atualiza o rascunho.
    availability = await client.post(
        f"/chat/lot-drafts/{draft_id}/availability",
        headers=headers,
        json={"confirmed": True, "expected_revision": patched.json()["revision"]},
    )
    assert availability.status_code == 200
    assert availability.json()["availability_confirmed"] is True
    assert availability.json()["lot_id"] is None

    # Autorização explícita: grava o lote de 20 kg com entrega no dia 6.
    confirmed = await client.post(f"/chat/lot-drafts/{draft_id}/confirm", headers=headers, json={"expected_revision": availability.json()["revision"]})
    assert confirmed.status_code == 200
    body = confirmed.json()
    assert body["status"] == "confirmado"
    assert Decimal(str(body["saved_lot"]["quantity"])) == Decimal(20)
    assert body["saved_lot"]["delivery_date"] == "2026-11-06"
    assert body["saved_lot"]["order_id"] == str(env.order_id)

    # Repetir a mesma confirmação devolve o mesmo lote.
    again = await client.post(f"/chat/lot-drafts/{draft_id}/confirm", headers=headers, json={"expected_revision": body["revision"]})
    assert again.status_code == 200
    assert again.json()["lot_id"] == body["lot_id"]

    # O lote continua visível ao reabrir a conversa e existe um único registro novo.
    reopened = await draft_from_chat(client, headers, session_id)
    assert reopened["status"] == "confirmado"
    assert reopened["saved_lot"]["delivery_date"] == "2026-11-06"
    total = await db_session.scalar(
        select(func.count(Lot.id)).where(Lot.item_id == env.item_id)
    )
    assert total == 3  # 50 kg + 25 kg + 20 kg


async def test_cancelled_order_is_rejected_with_conflict_and_draft_is_kept(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    env = await seed_catalog(db_session)
    headers = await create_user_headers(db_session)
    session_id = await new_session(client, headers)
    draft = await create_draft(
        client, headers, session_id, draft_body(env, quantity="10")
    )
    order = await db_session.get(Order, env.order_id)
    order.cancelled = True
    await db_session.commit()

    response = await client.post(f"/chat/lot-drafts/{draft['id']}/confirm", headers=headers, json={"expected_revision": draft["revision"]})

    assert response.status_code == 409
    assert "cancelado" in response.json()["detail"]
    assert (await draft_from_chat(client, headers, session_id))["status"] == "em_revisao"


async def test_date_outside_deadline_is_rejected_even_after_deadline_changed(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    env = await seed_catalog(db_session)
    headers = await create_user_headers(db_session)
    session_id = await new_session(client, headers)
    draft = await create_draft(
        client, headers, session_id, draft_body(env, quantity="10", delivery_date="2026-11-08")
    )
    order = await db_session.get(Order, env.order_id)
    order.delivery_end_date = date(2026, 11, 6)
    await db_session.commit()

    response = await client.post(f"/chat/lot-drafts/{draft['id']}/confirm", headers=headers, json={"expected_revision": draft["revision"]})

    assert response.status_code == 422
    assert "fora do prazo" in response.json()["detail"]
    assert (await draft_from_chat(client, headers, session_id))["delivery_date"] == "2026-11-08"


async def test_other_account_cannot_access_the_draft(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    env = await seed_catalog(db_session)
    owner = await create_user_headers(db_session)
    stranger = await create_user_headers(db_session)
    session_id = await new_session(client, owner)
    draft = await create_draft(client, owner, session_id, draft_body(env))

    patch = await client.patch(
        f"/chat/lot-drafts/{draft['id']}", headers=stranger, json={"quantity": "1"}
    )
    confirm = await client.post(f"/chat/lot-drafts/{draft['id']}/confirm", headers=stranger, json={"expected_revision": draft["revision"]})
    create = await client.post(
        f"/chat/sessions/{session_id}/lot-drafts", headers=stranger, json=draft_body(env)
    )

    assert patch.status_code == 404
    assert confirm.status_code == 404
    assert create.status_code == 404