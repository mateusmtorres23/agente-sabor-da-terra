from enum import StrEnum
from uuid import UUID
from sqlalchemy import Enum, ForeignKey, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SolicitationStatus(StrEnum):
    RECEIVED = "recebida"
    IN_REVIEW = "em_analise"
    FINISHED = "finalizada"


class SolicitationType(StrEnum):
    ORDER = "pedido"
    CONSULTATION = "consulta"
    OFFER = "oferta"
    NOTICE = "comunicado"
    UNIDENTIFIED = "nao_identificado"


class SolicitationUrgency(StrEnum):
    URGENT = "urgente"
    NORMAL = "normal"
    UNDETERMINED = "indeterminada"


class Solicitation(Base):
    __tablename__ = "solicitations"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            name="uq_solicitations_session_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
    Uuid,
    ForeignKey("received_entries.id", ondelete="RESTRICT"),
    primary_key=True,
    )

    status: Mapped[SolicitationStatus] = mapped_column(
        Enum(
            SolicitationStatus,
            name="solicitation_status",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
            validate_strings=True,
        ),
        default=SolicitationStatus.RECEIVED,
        nullable=False,
    )

    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    request_type: Mapped[SolicitationType] = mapped_column(
        Enum(
            SolicitationType,
            name="solicitation_type",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
            validate_strings=True,
        ),
        nullable=False,
    )

    urgency: Mapped[SolicitationUrgency] = mapped_column(
        Enum(
            SolicitationUrgency,
            name="solicitation_urgency",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
            validate_strings=True,
        ),
        nullable=False,
    )

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )
