from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .chat_message import ChatMessage
    from .chat_session import ChatSession
    from .lot import Lot
    from .order import Order
    from .order_item import OrderItem
    from .producer import Producer


class LotDraft(Base):
    __tablename__ = "lot_drafts"
    __table_args__ = (
        UniqueConstraint("message_id", name="uq_lot_drafts_message_id"),
        CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name="ck_lot_drafts_quantity_positive",
        ),
        CheckConstraint(
            "unit IS NULL OR unit ~ '[^[:space:]]'",
            name="ck_lot_drafts_unit_not_blank",
        ),
        CheckConstraint(
            "status IN ('em_revisao', 'confirmado')",
            name="ck_lot_drafts_status_valid",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("order_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    producer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("producers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    availability_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    needs_date_review: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), default="em_revisao", nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    lot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("lots.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    session: Mapped["ChatSession"] = relationship()
    message: Mapped["ChatMessage"] = relationship(back_populates="lot_draft")
    order: Mapped["Order | None"] = relationship()
    item: Mapped["OrderItem | None"] = relationship()
    producer: Mapped["Producer | None"] = relationship()
    lot: Mapped["Lot | None"] = relationship()