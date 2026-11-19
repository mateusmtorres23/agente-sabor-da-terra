
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.received_entry import ReceivedEntry, ReceivedEntryStatus
from api.repositories.received_entry import ReceivedEntryRepository

pytestmark = pytest.mark.asyncio(loop_scope="function")


async def test_add_persists_received_entry(db_session: AsyncSession) -> None:
    repository = ReceivedEntryRepository(db_session)

    entry = ReceivedEntry(
        original_text="Preciso de informações sobre o edital.",
        sender="usuario-teste",
        source_channel="whatsapp",
        received_at=datetime.now(UTC),
    )

    repository.add(entry)
    await db_session.flush()

    result = await repository.get_by_id(entry.id)

    assert result is not None
    assert result.id == entry.id
    assert result.original_text == "Preciso de informações sobre o edital."
    assert result.sender == "usuario-teste"
    assert result.source_channel == "whatsapp"


async def test_get_by_id_returns_none_for_unknown_id(
    db_session: AsyncSession,
) -> None:
    repository = ReceivedEntryRepository(db_session)

    assert await repository.get_by_id(uuid4()) is None


async def test_get_by_id_supports_row_lock(
    db_session: AsyncSession,
) -> None:
    repository = ReceivedEntryRepository(db_session)

    entry = ReceivedEntry(
        original_text="Mensagem para testar bloqueio.",
        sender="usuario-teste",
        source_channel="whatsapp",
        received_at=datetime.now(UTC),
    )

    repository.add(entry)
    await db_session.flush()

    result = await repository.get_by_id(entry.id, lock=True)

    assert result is not None
    assert result.id == entry.id


async def test_list_by_status_returns_empty_list(
    db_session: AsyncSession,
) -> None:
    repository = ReceivedEntryRepository(db_session)

    result = await repository.list_by_status(
        ReceivedEntryStatus.PENDING
    )

    assert result == []


async def test_list_by_status_filters_and_orders_entries(
    db_session: AsyncSession,
) -> None:
    repository = ReceivedEntryRepository(db_session)

    first = ReceivedEntry(
        id=uuid4(),
        original_text="Primeira mensagem",
        sender="usuario-1",
        source_channel="whatsapp",
        received_at=datetime(2026, 1, 1, tzinfo=UTC),
        triage_status=ReceivedEntryStatus.PENDING,
    )

    second = ReceivedEntry(
        id=uuid4(),
        original_text="Segunda mensagem",
        sender="usuario-2",
        source_channel="whatsapp",
        received_at=datetime(2026, 1, 2, tzinfo=UTC),
        triage_status=ReceivedEntryStatus.PENDING,
    )

    failed = ReceivedEntry(
        id=uuid4(),
        original_text="Mensagem com falha",
        sender="usuario-3",
        source_channel="whatsapp",
        received_at=datetime(2026, 1, 3, tzinfo=UTC),
        triage_status=ReceivedEntryStatus.FAILED,
    )

    db_session.add_all([second, failed, first])
    await db_session.flush()

    result = await repository.list_by_status(
        ReceivedEntryStatus.PENDING
    )

    assert [entry.id for entry in result] == [first.id, second.id]
