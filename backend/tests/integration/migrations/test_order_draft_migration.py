import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from alembic import command
from api.models import (
    ChatSession,
    Order,
    OrderDraft,
    OrderItem,
    Product,
    User,
)

DRAFT_REVISION = "e3b0b6c06f7c"
BACKEND_DIR = Path(__file__).resolve().parents[3]

EXISTING_TABLES = (
    "users",
    "chat_sessions",
    "products",
    "orders",
    "order_items",
)


async def seed_existing_data(url: str) -> tuple[UUID, UUID]:
    engine = create_async_engine(url)

    try:
        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as session:
            user = User(
                email="draft-migration@example.com",
                password_hash="unused",
            )
            product = Product(name="Queijo coalho")

            session.add_all([user, product])
            await session.flush()

            chat = ChatSession(
                user_id=user.id,
                title="Conversa anterior",
            )
            session.add(chat)
            await session.flush()

            order = Order(
                session_id=chat.id,
                buyer="Mercado anterior",
                products="  Descrição original preservada\n",
                conditions="Entrega pela manhã",
                delivery_start_date=date(2026, 11, 6),
                items=[
                    OrderItem(
                        product_id=product.id,
                        quantity=Decimal("10.125"),
                        unit="kg",
                    )
                ],
            )
            session.add(order)
            await session.commit()

            return chat.id, order.id
    finally:
        await engine.dispose()


async def snapshot(url: str) -> tuple[set[str], dict, str]:
    engine = create_async_engine(url)

    try:
        async with engine.connect() as connection:
            tables = await connection.run_sync(
                lambda conn: set(inspect(conn).get_table_names())
            )

            records = {}

            for table in EXISTING_TABLES:
                result = await connection.execute(
                    text(f"SELECT * FROM {table} ORDER BY id")
                )
                records[table] = [
                    dict(row) for row in result.mappings()
                ]

            revision = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )

            return tables, records, revision
    finally:
        await engine.dispose()


async def check_drafts(
    url: str,
    session_id: UUID,
    order_id: UUID,
) -> None:
    engine = create_async_engine(url)

    data = {
        "buyer": "Mercado",
        "items": [],
        "pending": ["Confirmar itens."],
    }
    confirmed = {
        "buyer": "Comprador revisado",
        "items": [],
    }

    try:
        async with AsyncSession(
            engine,
            expire_on_commit=False,
        ) as session:
            count = await session.scalar(
                select(func.count()).select_from(OrderDraft)
            )
            assert count == 0

            pending = OrderDraft(
                session_id=session_id,
                data=data,
                confirmation_payload=None,
            )
            completed = OrderDraft(
                session_id=session_id,
                data=data,
                confirmed_order_id=order_id,
                confirmation_payload=confirmed,
            )

            session.add_all([pending, completed])
            await session.commit()

            pending_id = pending.id
            completed_id = completed.id


        async with AsyncSession(engine) as session:
            saved = await session.get(OrderDraft, pending_id)

            assert saved is not None
            assert saved.data == data
            assert saved.version == 1
            assert saved.confirmed_order_id is None
            assert saved.confirmation_payload is None
            assert saved.created_at is not None

            completed = await session.get(
                OrderDraft,
                completed_id,
            )

            assert completed is not None
            assert completed.confirmed_order_id == order_id
            assert completed.confirmation_payload == confirmed

            is_sql_null = await session.scalar(
                text(
                    "SELECT confirmation_payload IS NULL "
                    "FROM order_drafts WHERE id = :id"
                ),
                {"id": pending_id},
            )
            assert is_sql_null is True

        invalid_cases = (
            {"version": 0},
            {
                "confirmation_payload": {
                    "buyer": "Sem pedido vinculado"
                }
            },
        )

        for invalid in invalid_cases:
            with pytest.raises(IntegrityError):
                async with AsyncSession(engine) as session:
                    session.add(
                        OrderDraft(
                            session_id=session_id,
                            data=data,
                            **invalid,
                        )
                    )
                    await session.commit()

        async with AsyncSession(engine) as session:
            count = await session.scalar(
                select(func.count()).select_from(OrderDraft)
            )
            assert count == 2
    finally:
        await engine.dispose()


def test_order_drafts_upgrade_downgrade_and_reupgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(BACKEND_DIR / "alembic"),
    )

    script = ScriptDirectory.from_config(config)
    revision = script.get_revision(DRAFT_REVISION)

    assert revision is not None

    parent = revision.down_revision
    assert parent == "0009_create_lots"
    assert script.get_heads() == [DRAFT_REVISION]
    assert DRAFT_REVISION in {
        entry.revision for entry in script.walk_revisions()
    }

    with PostgresContainer(
        image="postgres:16-alpine",
        username="test",
        password="test",
        dbname="test_order_draft_migration",
    ) as container:
        url = container.get_connection_url(driver="asyncpg")
        monkeypatch.setenv("DATABASE_URL", url)

        command.upgrade(config, parent)

        session_id, order_id = asyncio.run(
            seed_existing_data(url)
        )
        original_tables, original_data, current = asyncio.run(
            snapshot(url)
        )

        assert current == parent
        assert "order_drafts" not in original_tables

        command.upgrade(config, DRAFT_REVISION)

        tables, records, current = asyncio.run(snapshot(url))

        assert current == DRAFT_REVISION
        assert tables == original_tables | {"order_drafts"}
        assert records == original_data

        asyncio.run(check_drafts(url, session_id, order_id))

        command.downgrade(config, parent)

        tables, records, current = asyncio.run(snapshot(url))

        assert current == parent
        assert tables == original_tables
        assert records == original_data

        command.upgrade(config, DRAFT_REVISION)

        tables, records, current = asyncio.run(snapshot(url))

        assert current == DRAFT_REVISION
        assert tables == original_tables | {"order_drafts"}
        assert records == original_data

        asyncio.run(check_drafts(url, session_id, order_id))
