"""create lot drafts

Revision ID: 0010_create_lot_drafts
Revises: e3b0b6c06f7c
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_create_lot_drafts"
down_revision: str | Sequence[str] | None = "0010_chat_agent_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lot_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("item_id", sa.Uuid(), nullable=True),
        sa.Column("producer_id", sa.Uuid(), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=18, scale=3), nullable=True),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column(
            "availability_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "needs_date_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="em_revisao",
        ),
        sa.Column(
            "revision",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("lot_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name="ck_lot_drafts_quantity_positive",
        ),
        sa.CheckConstraint(
            "unit IS NULL OR unit ~ '[^[:space:]]'",
            name="ck_lot_drafts_unit_not_blank",
        ),
        sa.CheckConstraint(
            "status IN ('em_revisao', 'confirmado')",
            name="ck_lot_drafts_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["chat_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["chat_messages.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["item_id"], ["order_items.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["producer_id"], ["producers.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["lot_id"], ["lots.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", name="uq_lot_drafts_message_id"),
        sa.UniqueConstraint("lot_id", name="uq_lot_drafts_lot_id"),
    )
    op.create_index("ix_lot_drafts_session_id", "lot_drafts", ["session_id"])
    op.create_index("ix_lot_drafts_message_id", "lot_drafts", ["message_id"])
    op.create_index("ix_lot_drafts_order_id", "lot_drafts", ["order_id"])
    op.create_index("ix_lot_drafts_item_id", "lot_drafts", ["item_id"])
    op.create_index("ix_lot_drafts_producer_id", "lot_drafts", ["producer_id"])


def downgrade() -> None:
    op.drop_index("ix_lot_drafts_producer_id", table_name="lot_drafts")
    op.drop_index("ix_lot_drafts_item_id", table_name="lot_drafts")
    op.drop_index("ix_lot_drafts_order_id", table_name="lot_drafts")
    op.drop_index("ix_lot_drafts_message_id", table_name="lot_drafts")
    op.drop_index("ix_lot_drafts_session_id", table_name="lot_drafts")
    op.drop_table("lot_drafts")