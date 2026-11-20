from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class OrderDraft(Base):
    __tablename__ = "order_drafts"

    __table_args__ = (
        CheckConstraint(
            "version >= 1",
            name="ck_order_drafts_version_positive",
        ),
        CheckConstraint(
            "(confirmed_order_id IS NULL) "
            "= (confirmation_payload IS NULL)",
            name="ck_order_drafts_confirmation_complete",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid4,
    )

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )

    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    confirmed_order_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )

    confirmation_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )