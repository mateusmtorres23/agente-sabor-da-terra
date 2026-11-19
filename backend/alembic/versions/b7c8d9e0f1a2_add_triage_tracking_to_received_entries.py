"""add triage tracking columns to received_entries

Revision ID: b7c8d9e0f1a2
Revises: a524eaf1414d
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: str | Sequence[str] | None = "a524eaf1414d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "received_entries",
        sa.Column("source_context", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "received_entries",
        sa.Column("external_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "received_entries",
        sa.Column("attempt_token", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "received_entries",
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "received_entries",
        sa.Column("failure_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "received_entries",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("received_entries", "updated_at")
    op.drop_column("received_entries", "failure_reason")
    op.drop_column("received_entries", "enqueued_at")
    op.drop_column("received_entries", "attempt_token")
    op.drop_column("received_entries", "external_id")
    op.drop_column("received_entries", "source_context")