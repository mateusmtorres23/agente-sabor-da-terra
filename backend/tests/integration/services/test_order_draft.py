"""Confirmations use real commits and independent PostgreSQL connections."""

import asyncio
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.models.chat_session import ChatSession
from api.models.order import Order
from api.models.order_draft import OrderDraft
from api.models.order_item import OrderItem
from api.models.product import Product
from api.models.solicitation import (
    Solicitation,
    SolicitationStatus,
    SolicitationType,
    SolicitationUrgency,
)
from api.models.user import User
from api.repositories.chat import ChatRepository
from api.repositories.order import OrderRepository
from api.repositories.order_draft import OrderDraftRepository
from api.repositories.product import ProductRepository
from api.repositories.solicitation import SolicitationRepository
from api.schemas.order_draft import OrderDraftConfirmation, OrderDraftData
from api.services.order import OrderService
from api.services.order_draft import (
    OrderDraftAlreadyConfirmedError,
    OrderDraftConflictError,
    OrderDraftConversationFinishedError,
    OrderDraftNotFoundError,
    OrderDraftService,
    OrderDraftValidationError,
)

pytestmark = pytest.mark.asyncio


def service(session):
    return OrderDraftService(
        OrderDraftRepository(session),
        OrderService(OrderRepository(session), ProductRepository(session)),
        ChatRepository(session),
        SolicitationRepository(session),
    )


@dataclass
class Case:
    factory: async_sessionmaker
    owner: UUID
    other_user: UUID
    chat_id: UUID
    solicitation_id: UUID | None
    products: tuple[UUID, UUID]
    draft_id: UUID
    data: OrderDraftData

    @property
    def scope(self):
        if self.solicitation_id is not None:
            return {"solicitation_id": self.solicitation_id}
        return {"session_id": self.chat_id}

    def confirmation(self, *, include_honey=False):
        selected = self.data.items if include_honey else self.data.items[:1]
        return OrderDraftConfirmation.model_validate(
            {
                "buyer": "Mercado Bom Preço",
                "conditions": "Entrega pela manhã.",
                "delivery_start_date": "2026-11-06",
                "delivery_end_date": None,
                "draft_version": 1,
                "confirmed": True,
                "items": [
                    {
                        "draft_item_id": item.id,
                        "product_id": item.product_id,
                        "quantity": item.quantity,
                        "unit": item.unit,
                    }
                    for item in selected
                ],
            }
        )

    async def confirm(self, payload=None, *, draft_id=None, user_id=None):
        async with self.factory() as session:
            order, created = await service(session).confirm(
                user_id or self.owner,
                draft_id or self.draft_id,
                payload or self.confirmation(),
                **self.scope,
            )
            return order.id, created

    async def assert_no_order(self):
        async with self.factory() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Order)
                    .where(Order.session_id == self.chat_id)
                )
                == 0
            )
            draft = await session.get(OrderDraft, self.draft_id)
            assert draft.confirmed_order_id is None
            assert draft.confirmation_payload is None
            assert draft.data == self.data.model_dump(mode="json")


@pytest_asyncio.fixture(params=["private", "triage"])
async def case(engine, request):
    # No shared savepoint: another connection must see each committed operation.
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    owner, other_user, chat_id = uuid4(), uuid4(), uuid4()
    products = (uuid4(), uuid4())
    solicitation_id = uuid4() if request.param == "triage" else None
    data = OrderDraftData.model_validate(
        {
            "buyer": "Mercado Bom Preço",
            "conditions": "Entrega pela manhã.",
            "delivery_start_date": "2026-11-04",
            "delivery_end_date": "2026-11-08",
            "items": [
                {
                    "product_id": products[0],
                    "product_name": "Queijo coalho",
                    "quantity": "10",
                    "unit": "kg",
                },
                {
                    "product_id": products[1],
                    "product_name": "Mel",
                    "quantity": "5",
                    "unit": "pote",
                    "conditional": True,
                    "condition_text": "Se tiver.",
                },
            ],
        }
    )
    draft_id = uuid4()
    try:
        async with factory.begin() as session:
            session.add_all(
                [
                    User(
                        id=owner, email=f"{owner}@example.com", password_hash="unused"
                    ),
                    User(
                        id=other_user,
                        email=f"{other_user}@example.com",
                        password_hash="unused",
                    ),
                    Product(id=products[0], name=f"Queijo {products[0]}"),
                    Product(id=products[1], name=f"Mel {products[1]}"),
                ]
            )
            await session.flush()
            session.add(
                ChatSession(
                    id=chat_id,
                    user_id=None if solicitation_id else owner,
                )
            )
            await session.flush()
            if solicitation_id:
                session.add(
                    Solicitation(
                        id=solicitation_id,
                        session_id=chat_id,
                        summary="Pedido de queijo e mel.",
                        request_type=SolicitationType.ORDER,
                        urgency=SolicitationUrgency.NORMAL,
                        status=SolicitationStatus.RECEIVED,
                    )
                )
            session.add(
                OrderDraft(
                    id=draft_id,
                    session_id=chat_id,
                    data=data.model_dump(mode="json"),
                )
            )
        yield Case(
            factory,
            owner,
            other_user,
            chat_id,
            solicitation_id,
            products,
            draft_id,
            data,
        )
    finally:
        async with factory.begin() as session:
            # Remove draft first because its order FK uses RESTRICT.
            await session.execute(
                delete(OrderDraft).where(OrderDraft.session_id == chat_id)
            )
            await session.execute(delete(Order).where(Order.session_id == chat_id))
            await session.execute(
                delete(Solicitation).where(Solicitation.session_id == chat_id)
            )
            await session.execute(delete(ChatSession).where(ChatSession.id == chat_id))
            await session.execute(delete(Product).where(Product.id.in_(products)))
            await session.execute(delete(User).where(User.id.in_([owner, other_user])))


async def test_review_saves_only_selected_items_and_preserves_origin(case):
    order_id, created = await case.confirm()
    assert created is True
    async with case.factory() as session:
        order = await OrderRepository(session).get_by_session(case.chat_id)
        assert order.id == order_id
        assert order.buyer == "Mercado Bom Preço"
        assert order.conditions == "Entrega pela manhã."
        assert order.delivery_start_date == date(2026, 11, 6)
        assert order.delivery_end_date is None
        assert [
            (item.product_id, item.quantity, item.unit) for item in order.items
        ] == [
            (case.products[0], Decimal(10), "kg"),
        ]
        draft = await session.get(OrderDraft, case.draft_id)
        assert draft.confirmed_order_id == order_id
        assert draft.confirmation_payload["delivery_start_date"] == "2026-11-06"
        assert draft.data == case.data.model_dump(mode="json")
        if case.solicitation_id:
            solicitation = await session.get(Solicitation, case.solicitation_id)
            assert solicitation.session_id == order.session_id
            assert solicitation.status == SolicitationStatus.IN_REVIEW


async def test_repeated_confirmation_is_idempotent(case):
    order_id, _ = await case.confirm()
    assert await case.confirm() == (order_id, False)
    async with case.factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Order)
                .where(Order.session_id == case.chat_id)
            )
            == 1
        )


async def test_equivalent_quantity_and_item_order_are_same_confirmation(case):
    payload = case.confirmation(include_honey=True)
    order_id, _ = await case.confirm(payload)
    repeated = payload.model_dump(mode="json")
    repeated["items"].reverse()
    for item in repeated["items"]:
        item["quantity"] = f"{Decimal(item['quantity']):.3f}"
    assert await case.confirm(OrderDraftConfirmation.model_validate(repeated)) == (
        order_id,
        False,
    )


async def test_replay_uses_saved_confirmation_after_order_is_edited(case):
    order_id, _ = await case.confirm()
    async with case.factory.begin() as session:
        order = await session.get(Order, order_id)
        order.buyer = "Comprador atualizado posteriormente"
        order.version += 1
    assert await case.confirm() == (order_id, False)
    async with case.factory() as session:
        linked = await service(session).get_linked_order(case.owner, **case.scope)
        assert linked.buyer == "Comprador atualizado posteriormente"
        assert linked.version == 2


async def test_changed_confirmation_returns_existing_order_id(case):
    order_id, _ = await case.confirm()
    changed = case.confirmation().model_copy(update={"buyer": "Outro comprador"})
    with pytest.raises(OrderDraftAlreadyConfirmedError) as raised:
        await case.confirm(changed)
    assert raised.value.order_id == order_id
    async with case.factory() as session:
        assert (await session.get(Order, order_id)).buyer == "Mercado Bom Preço"


async def test_another_draft_cannot_create_second_order(case):
    other_draft_id = uuid4()
    async with case.factory.begin() as session:
        session.add(
            OrderDraft(
                id=other_draft_id,
                session_id=case.chat_id,
                data=case.data.model_dump(mode="json"),
            )
        )
    order_id, _ = await case.confirm()
    with pytest.raises(OrderDraftAlreadyConfirmedError) as raised:
        await case.confirm(draft_id=other_draft_id)
    assert raised.value.order_id == order_id


@pytest.mark.parametrize(
    "invalid", ["stale", "unknown-item", "missing-required", "unknown-product"]
)
async def test_invalid_confirmation_leaves_draft_and_database_unchanged(case, invalid):
    payload = case.confirmation().model_dump(mode="json")
    expected = OrderDraftValidationError
    if invalid == "stale":
        payload["draft_version"] = 2
        expected = OrderDraftConflictError
    elif invalid == "unknown-item":
        payload["items"][0]["draft_item_id"] = str(uuid4())
    elif invalid == "missing-required":
        payload = case.confirmation(include_honey=True).model_dump(mode="json")
        payload["items"] = payload["items"][1:]
    else:
        payload["items"][0]["product_id"] = str(uuid4())
    with pytest.raises(expected):
        await case.confirm(OrderDraftConfirmation.model_validate(payload))
    await case.assert_no_order()
    if case.solicitation_id:
        async with case.factory() as session:
            assert (
                await session.get(Solicitation, case.solicitation_id)
            ).status == SolicitationStatus.RECEIVED


async def test_failure_after_order_flush_rolls_back_order_items_and_confirmation(
    case, monkeypatch
):
    async with case.factory() as session:

        async def fail_commit():
            # create_order(commit=False) must have flushed actual order and items.
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Order)
                    .where(Order.session_id == case.chat_id)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(OrderItem)
                    .join(Order, OrderItem.order_id == Order.id)
                    .where(Order.session_id == case.chat_id)
                )
                == 1
            )
            raise RuntimeError("simulated commit failure")

        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="simulated commit failure"):
            await service(session).confirm(
                case.owner,
                case.draft_id,
                case.confirmation(),
                **case.scope,
            )
    await case.assert_no_order()
    async with case.factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(OrderItem)
                .where(OrderItem.product_id.in_(case.products))
            )
            == 0
        )
        if case.solicitation_id:
            solicitation = await session.get(Solicitation, case.solicitation_id)
            assert solicitation.status == SolicitationStatus.RECEIVED
    # The same draft remains usable after the failed transaction.
    assert (await case.confirm())[1] is True


async def test_private_chat_rejects_another_user_and_triage_is_shared(case):
    if case.solicitation_id:
        assert (await case.confirm(user_id=case.other_user))[1] is True
    else:
        with pytest.raises(OrderDraftNotFoundError):
            await case.confirm(user_id=case.other_user)
        async with case.factory() as session:
            with pytest.raises(OrderDraftNotFoundError):
                await service(session).get_linked_order(case.other_user, **case.scope)
        await case.assert_no_order()


async def test_draft_from_another_conversation_is_rejected(case):
    foreign_chat, foreign_draft = uuid4(), uuid4()
    try:
        async with case.factory.begin() as session:
            session.add(ChatSession(id=foreign_chat, user_id=case.owner))
            await session.flush()
            session.add(
                OrderDraft(
                    id=foreign_draft,
                    session_id=foreign_chat,
                    data=case.data.model_dump(mode="json"),
                )
            )
        with pytest.raises(OrderDraftNotFoundError):
            await case.confirm(draft_id=foreign_draft)
        await case.assert_no_order()
    finally:
        async with case.factory.begin() as session:
            await session.execute(
                delete(OrderDraft).where(OrderDraft.id == foreign_draft)
            )
            await session.execute(
                delete(ChatSession).where(ChatSession.id == foreign_chat)
            )


async def test_cancellation_preserves_link_and_does_not_allow_new_order(case):
    order_id, _ = await case.confirm()
    async with case.factory() as session:
        await service(session).order_service.cancel_order(order_id)
    assert await case.confirm() == (order_id, False)
    async with case.factory() as session:
        linked = await service(session).get_linked_order(case.owner, **case.scope)
        assert linked.id == order_id
        assert linked.cancelled is True
        assert linked.version == 2
    async with case.factory() as session:
        with pytest.raises(OrderDraftAlreadyConfirmedError) as raised:
            await service(session).create_draft(case.owner, case.data, **case.scope)
        assert raised.value.order_id == order_id


async def test_finished_triage_rejects_confirmation_but_preserves_order_link(case):
    if case.solicitation_id is None:
        pytest.skip("Finalização se aplica somente à triagem.")
    async with case.factory.begin() as session:
        solicitation = await session.get(Solicitation, case.solicitation_id)
        solicitation.status = SolicitationStatus.FINISHED
    with pytest.raises(OrderDraftConversationFinishedError):
        await case.confirm()
    await case.assert_no_order()
    async with case.factory.begin() as session:
        solicitation = await session.get(Solicitation, case.solicitation_id)
        solicitation.status = SolicitationStatus.IN_REVIEW
    order_id, _ = await case.confirm()
    async with case.factory.begin() as session:
        solicitation = await session.get(Solicitation, case.solicitation_id)
        solicitation.status = SolicitationStatus.FINISHED
    with pytest.raises(OrderDraftConversationFinishedError):
        await case.confirm()
    async with case.factory() as session:
        linked = await service(session).get_linked_order(case.other_user, **case.scope)
        assert linked.id == order_id
        assert (
            await service(session).get_latest_draft(case.other_user, **case.scope)
        ).id == case.draft_id


@pytest.mark.parametrize("kind", ["same", "changed", "another-draft"])
async def test_simultaneous_confirmations_create_exactly_one_order(case, kind):
    second_id = case.draft_id
    second_payload = case.confirmation()
    if kind == "changed":
        second_payload = second_payload.model_copy(update={"buyer": "Outro comprador"})
    elif kind == "another-draft":
        second_id = uuid4()
        async with case.factory.begin() as session:
            session.add(
                OrderDraft(
                    id=second_id,
                    session_id=case.chat_id,
                    data=case.data.model_dump(mode="json"),
                )
            )

    ready = asyncio.Event()

    async def attempt(draft_id, payload):
        async with case.factory() as session:
            await ready.wait()
            try:
                order, created = await service(session).confirm(
                    case.owner,
                    draft_id,
                    payload,
                    **case.scope,
                )
                return order.id, created
            except OrderDraftAlreadyConfirmedError as error:
                return error

    tasks = [
        asyncio.create_task(attempt(case.draft_id, case.confirmation())),
        asyncio.create_task(attempt(second_id, second_payload)),
    ]
    ready.set()
    results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=30)
    successes = [result for result in results if isinstance(result, tuple)]
    conflicts = [
        result
        for result in results
        if isinstance(result, OrderDraftAlreadyConfirmedError)
    ]
    if kind == "same":
        assert len(successes) == 2
        assert successes[0][0] == successes[1][0]
        assert sorted(result[1] for result in successes) == [False, True]
    else:
        assert len(successes) == len(conflicts) == 1
        assert successes[0][1] is True
        assert conflicts[0].order_id == successes[0][0]
    async with case.factory() as session:
        orders = list(
            (
                await session.scalars(
                    select(Order).where(Order.session_id == case.chat_id)
                )
            ).all()
        )
        assert len(orders) == 1
        assert orders[0].id == successes[0][0]
        linked_drafts = list(
            (
                await session.scalars(
                    select(OrderDraft).where(
                        OrderDraft.session_id == case.chat_id,
                        OrderDraft.confirmed_order_id.is_not(None),
                    )
                )
            ).all()
        )
        assert len(linked_drafts) == 1
        assert linked_drafts[0].confirmed_order_id == orders[0].id
        assert linked_drafts[0].confirmation_payload["buyer"] == orders[0].buyer
