"""add conversational agent metadata columns to chat_messages

Revision ID: 0010_chat_agent_metadata
Revises: e3b0b6c06f7c
Create Date: 2026-11-19 18:35:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_chat_agent_metadata"
down_revision: str | Sequence[str] | None = "e3b0b6c06f7c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column("flow", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "chat_messages",
        sa.Column(
            "reference_received_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_chat_messages_flow",
        "chat_messages",
        "flow IS NULL OR flow IN ('triage', 'consultation')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_chat_messages_flow",
        "chat_messages",
        type_="check",
    )
    op.drop_column("chat_messages", "reference_received_at")
    op.drop_column("chat_messages", "flow")
