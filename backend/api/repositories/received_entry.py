from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.received_entry import ReceivedEntry, ReceivedEntryStatus


class ReceivedEntryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, entry: ReceivedEntry) -> None:
        self.session.add(entry)

    async def get_by_id(
        self,
        entry_id: UUID,
        *,
        lock: bool = False,
    ) -> ReceivedEntry | None:
        statement = select(ReceivedEntry).where(
            ReceivedEntry.id == entry_id
        )

        if lock:
            statement = statement.with_for_update()

        return await self.session.scalar(statement)

    async def list_by_status(
        self,
        status: ReceivedEntryStatus,
        *,
        limit: int = 100,
    ) -> list[ReceivedEntry]:
        statement = (
            select(ReceivedEntry)
            .where(ReceivedEntry.triage_status == status)
            .order_by(ReceivedEntry.received_at.asc())
            .limit(limit)
        )

        return list((await self.session.scalars(statement)).all())

    async def list_failed_and_retrying(
        self,
        *,
        limit: int = 100,
    ) -> list[ReceivedEntry]:
        statement = (
            select(ReceivedEntry)
            .where(
                ReceivedEntry.triage_status.in_(
                    [
                        ReceivedEntryStatus.FAILED,
                        ReceivedEntryStatus.PROCESSING,
                    ]
                )
            )
            .order_by(ReceivedEntry.received_at.desc(), ReceivedEntry.id.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())

    async def list_recoverable_for_scheduler(
        self,
        *,
        pending_before: datetime,
        processing_before: datetime,
        limit: int = 100,
    ) -> list[ReceivedEntry]:
        statement = (
            select(ReceivedEntry)
            .where(
                or_(
                    (
                        (ReceivedEntry.triage_status == ReceivedEntryStatus.PENDING)
                        & (
                            ReceivedEntry.enqueued_at.is_(None)
                            | (ReceivedEntry.enqueued_at <= pending_before)
                        )
                    ),
                    (
                        (ReceivedEntry.triage_status == ReceivedEntryStatus.PROCESSING)
                        & (ReceivedEntry.updated_at <= processing_before)
                    ),
                )
            )
            .order_by(ReceivedEntry.received_at.asc())
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())