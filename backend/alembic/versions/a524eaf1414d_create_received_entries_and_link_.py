
"""create received entries and link solicitations

Revision ID: a524eaf1414d
Revises: 0008_merge_triage_main
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision: str = "a524eaf1414d"
down_revision: str | Sequence[str] | None = "0008_merge_triage_main"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TRIAGE_STATUS = postgresql.ENUM(
    "pendente",
    "em_processamento",
    "concluida",
    "falhou",
    name="received_entry_status",
    create_type=False,
)


def upgrade() -> None:
    # Cria o ENUM uma única vez.
    op.execute(
        """
        CREATE TYPE received_entry_status AS ENUM (
            'pendente',
            'em_processamento',
            'concluida',
            'falhou'
        )
        """
    )

    # Cria a tabela de entradas recebidas.
    op.create_table(
        "received_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("sender", sa.String(255), nullable=False),
        sa.Column("source_channel", sa.String(100), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "triage_status",
            TRIAGE_STATUS,
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Verifica solicitações antigas no próprio PostgreSQL.
    # Funciona tanto online quanto na geração offline de SQL.
    op.execute(
        """
        DO $$
        DECLARE
            pending_ids TEXT;
        BEGIN
            SELECT string_agg(id::text, ', ' ORDER BY id)
            INTO pending_ids
            FROM solicitations;

            IF pending_ids IS NOT NULL THEN
                RAISE EXCEPTION
                    'Migração interrompida: solicitações '
                    'sem entrada de origem comprovada. '
                    'IDs pendentes: %',
                    pending_ids;
            END IF;
        END
        $$
        """
    )

    # O UUID da solicitação também identifica sua entrada.
    op.create_foreign_key(
        "fk_solicitations_id_received_entries",
        "solicitations",
        "received_entries",
        ["id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    # Não permite perder dados durante uma reversão.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM solicitations)
               OR EXISTS (SELECT 1 FROM received_entries)
            THEN
                RAISE EXCEPTION
                    'Downgrade interrompido: existem '
                    'solicitações ou entradas recebidas. '
                    'Preserve os dados antes de reverter.';
            END IF;
        END
        $$
        """
    )

    op.drop_constraint(
        "fk_solicitations_id_received_entries",
        "solicitations",
        type_="foreignkey",
    )

    op.drop_table("received_entries")

    op.execute(
        "DROP TYPE received_entry_status"
    )
