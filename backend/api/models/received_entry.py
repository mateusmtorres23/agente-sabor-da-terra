from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ReceivedEntryStatus(StrEnum):
    PENDING = "pendente"
    PROCESSING = "em_processamento"
    COMPLETED = "concluida"
    FAILED = "falhou"


class ReceivedEntry(Base):
    __tablename__ = "received_entries"

    id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid4,
    )

    original_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    sender: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    source_channel: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    source_context: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    external_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    triage_status: Mapped[ReceivedEntryStatus] = mapped_column(
        Enum(
            ReceivedEntryStatus,
            name="received_entry_status",
            values_callable=lambda enum_cls: [
                item.value for item in enum_cls
            ],
            validate_strings=True,
        ),
        default=ReceivedEntryStatus.PENDING,
        nullable=False,
    )

    attempt_token: Mapped[UUID | None] = mapped_column(
        Uuid,
        nullable=True,
    )

    enqueued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    failure_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )