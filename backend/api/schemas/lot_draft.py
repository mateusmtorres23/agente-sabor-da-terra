from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from typing import Any

class LotDraftCreate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        populate_by_name=True,
        extra="forbid",
    )

    content: str | None = Field(
        default="Rascunho de lote preparado para revisão e confirmação.",
        max_length=4000,
    )
    order_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("order_id", "pedido_id"),
    )
    item_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("item_id", "item_pedido_id"),
    )
    producer_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("producer_id", "produtor_id"),
    )
    quantity: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=18,
        decimal_places=3,
        allow_inf_nan=False,
        validation_alias=AliasChoices("quantity", "quantidade"),
    )
    unit: str | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("unit", "unidade"),
    )
    delivery_date: date | None = Field(
        default=None,
        validation_alias=AliasChoices("delivery_date", "data_entrega"),
    )
    availability_confirmed: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "availability_confirmed",
            "disponibilidade_confirmada",
        ),
    )


class LotDraftUpdate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        populate_by_name=True,
        extra="forbid",
    )

    order_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("order_id", "pedido_id"),
    )
    item_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("item_id", "item_pedido_id"),
    )
    producer_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("producer_id", "produtor_id"),
    )
    quantity: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=18,
        decimal_places=3,
        allow_inf_nan=False,
        validation_alias=AliasChoices("quantity", "quantidade"),
    )
    unit: str | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("unit", "unidade"),
    )
    delivery_date: date | None = Field(
        default=None,
        validation_alias=AliasChoices("delivery_date", "data_entrega"),
    )


class LotDraftAvailabilityUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    confirmed: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "confirmed",
            "availability_confirmed",
            "disponibilidade_confirmada",
        ),
    )


class LotDraftOrderDeadlineOut(BaseModel):
    delivery_start_date: date
    delivery_end_date: date | None = None
    cancelled: bool


class LotDraftSavedLotOut(BaseModel):
    id: UUID
    order_id: UUID | None = None
    item_id: UUID | None = None
    producer_id: UUID
    producer_name: str
    quantity: Decimal
    unit: str | None
    delivery_date: date
    availability_confirmed: bool | None


class LotDraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    message_id: UUID
    order_id: UUID | None
    item_id: UUID | None
    producer_id: UUID | None
    quantity: Decimal | None
    unit: str | None
    delivery_date: date | None
    availability_confirmed: bool
    needs_date_review: bool
    lot_id: UUID | None
    status: str
    order_deadline: LotDraftOrderDeadlineOut | None = None
    saved_lot: LotDraftSavedLotOut | None = None
    created_at: datetime
    updated_at: datetime


def build_lot_draft_out(draft: Any) -> LotDraftOut:
    """Converte um LotDraft (ORM, com relações carregadas) em LotDraftOut."""
    order_deadline: LotDraftOrderDeadlineOut | None = None
    if draft.order is not None:
        order_deadline = LotDraftOrderDeadlineOut(
            delivery_start_date=draft.order.delivery_start_date,
            delivery_end_date=draft.order.delivery_end_date,
            cancelled=draft.order.cancelled,
        )

    saved_lot: LotDraftSavedLotOut | None = None
    if draft.lot is not None:
        lot = draft.lot
        item_order_id = lot.item.order_id if lot.item is not None else draft.order_id
        saved_lot = LotDraftSavedLotOut(
            id=lot.id,
            order_id=item_order_id,
            item_id=lot.item_id,
            producer_id=lot.producer_id,
            producer_name=lot.producer.name if lot.producer else "",
            quantity=lot.quantity,
            unit=lot.unit,
            delivery_date=lot.delivery_date,
            availability_confirmed=lot.availability_confirmed,
        )

    return LotDraftOut(
        id=draft.id,
        session_id=draft.session_id,
        message_id=draft.message_id,
        order_id=draft.order_id,
        item_id=draft.item_id,
        producer_id=draft.producer_id,
        quantity=draft.quantity,
        unit=draft.unit,
        delivery_date=draft.delivery_date,
        availability_confirmed=draft.availability_confirmed,
        needs_date_review=draft.needs_date_review,
        lot_id=draft.lot_id,
        status="confirmado" if draft.lot_id is not None else "em_revisao",
        order_deadline=order_deadline,
        saved_lot=saved_lot,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )