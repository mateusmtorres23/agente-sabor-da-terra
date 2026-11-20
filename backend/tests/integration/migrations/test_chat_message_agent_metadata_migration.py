import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer

from alembic import command

AGENT_METADATA_REVISION = "0010_chat_agent_metadata"
PARENT_REVISION = "e3b0b6c06f7c"
BACKEND_DIR = Path(__file__).resolve().parents[3]


async def _seed_legacy_chat_message(url: str) -> tuple[UUID, UUID]:
    user_id = uuid4()
    session_id = uuid4()
    message_id = uuid4()
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO users (id, email, password_hash) "
                    "VALUES (:id, :email, 'hash')"
                ),
                {"id": user_id, "email": f"{user_id}@example.com"},
            )
            await connection.execute(
                text(
                    "INSERT INTO chat_sessions (id, user_id, title, created_at) "
                    "VALUES (:id, :user_id, 'Conversa legada', now())"
                ),
                {"id": session_id, "user_id": user_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO chat_messages "
                    "(id, session_id, role, content, position, created_at) "
                    "VALUES (:id, :session_id, 'USER', 'Mensagem antiga sem metadados', 1, now())"
                ),
                {"id": message_id, "session_id": session_id},
            )
    finally:
        await engine.dispose()
    return session_id, message_id


async def _read_message_row(url: str, message_id: UUID) -> dict[str, object]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text("SELECT * FROM chat_messages WHERE id = :id"),
                    {"id": message_id},
                )
            ).mappings().one()
            return dict(row)
    finally:
        await engine.dispose()


async def _read_chat_message_columns(url: str) -> dict[str, dict[str, object]]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            columns = await connection.run_sync(
                lambda conn: inspect(conn).get_columns("chat_messages")
            )
            return {col["name"]: col for col in columns}
    finally:
        await engine.dispose()


async def _insert_message_with_flow(
    url: str,
    session_id: UUID,
    position: int,
    flow: str | None,
) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO chat_messages "
                    "(id, session_id, role, content, position, flow, created_at) "
                    "VALUES (:id, :session_id, 'AGENT', 'Conteúdo', :position, :flow, now())"
                ),
                {
                    "id": uuid4(),
                    "session_id": session_id,
                    "position": position,
                    "flow": flow,
                },
            )
    finally:
        await engine.dispose()


def test_chat_message_agent_metadata_migration_preserves_legacy_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Critério 5 da #50:
    # - mantém uma única head no Alembic
    # - registros antigos permanecem consultáveis após upgrade/downgrade/upgrade
    # - metadados ausentes nos registros antigos ficam NULL (não presumidos)
    # - constraint ck_chat_messages_flow bloqueia valores inválidos
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()
    assert len(heads) == 1
    assert AGENT_METADATA_REVISION in {
        entry.revision
        for entry in script.walk_revisions(base="base", head=heads[0])
    }

    revision = script.get_revision(AGENT_METADATA_REVISION)
    assert revision is not None
    assert revision.down_revision == PARENT_REVISION

    with PostgresContainer(
        image="postgres:16-alpine",
        username="test",
        password="test",
        dbname="test_chat_agent_metadata",
    ) as container:
        url = container.get_connection_url(driver="asyncpg")
        monkeypatch.setenv("DATABASE_URL", url)

        command.upgrade(config, PARENT_REVISION)
        session_id, legacy_msg_id = asyncio.run(_seed_legacy_chat_message(url))
        before_row = asyncio.run(_read_message_row(url, legacy_msg_id))

        command.upgrade(config, AGENT_METADATA_REVISION)
        columns = asyncio.run(_read_chat_message_columns(url))
        for col_name in ("flow", "reference_received_at"):
            assert col_name in columns
            assert columns[col_name]["nullable"] is True
        assert "source_id" not in columns
        assert "context_metadata" not in columns

        upgraded_row = asyncio.run(_read_message_row(url, legacy_msg_id))
        assert upgraded_row["content"] == before_row["content"]
        assert upgraded_row["position"] == before_row["position"]
        assert upgraded_row["flow"] is None
        assert upgraded_row["reference_received_at"] is None

        # Valores válidos aceitos e valor inválido rejeitado pela check constraint
        asyncio.run(_insert_message_with_flow(url, session_id, 2, "triage"))
        asyncio.run(_insert_message_with_flow(url, session_id, 3, "consultation"))
        with pytest.raises(IntegrityError):
            asyncio.run(_insert_message_with_flow(url, session_id, 4, "invalido"))

        command.downgrade(config, PARENT_REVISION)
        downgraded_columns = asyncio.run(_read_chat_message_columns(url))
        for col_name in ("flow", "reference_received_at"):
            assert col_name not in downgraded_columns
        downgraded_row = asyncio.run(_read_message_row(url, legacy_msg_id))
        assert downgraded_row == before_row

        command.upgrade(config, AGENT_METADATA_REVISION)
        reupgraded_row = asyncio.run(_read_message_row(url, legacy_msg_id))
        assert reupgraded_row["content"] == before_row["content"]
        assert reupgraded_row["flow"] is None
        assert reupgraded_row["reference_received_at"] is None
