from datetime import date
from typing import Annotated, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .order import (
    OrderBase,
    OrderCreate,
    OrderItemCreate,
    Quantity,
)

PendingText = Annotated[str, Field(min_length=1)]


class OrderDraftItem(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    id: UUID = Field(default_factory=uuid4)

    product_id: UUID | None = None
    product_name: str | None = Field(default=None, min_length=1)

    quantity: Quantity | None = None
    unit: str | None = Field(default=None, min_length=1)

    conditional: bool = Field(default=False, strict=True)
    condition_text: str | None = Field(
        default=None,
        min_length=1,
    )

    pending: list[PendingText] = Field(default_factory=list)


class OrderDraftData(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    buyer: str | None = Field(default=None, min_length=1)
    conditions: str = ""

    delivery_start_date: date | None = None
    delivery_end_date: date | None = None

    items: list[OrderDraftItem] = Field(default_factory=list)
    pending: list[PendingText] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_delivery_dates(self) -> Self:
        if (
            self.delivery_start_date is not None
            and self.delivery_end_date is not None
            and self.delivery_end_date < self.delivery_start_date
        ):
            raise ValueError(
                "A data final deve ser igual ou posterior à data inicial."
            )

        return self

    @model_validator(mode="after")
    def validate_item_ids(self) -> Self:
        item_ids = [item.id for item in self.items]

        if len(item_ids) != len(set(item_ids)):
            raise ValueError(
                "O mesmo ID de item não pode aparecer mais de uma vez."
            )

        return self

class OrderDraftItemConfirmation(OrderItemCreate):
    draft_item_id: UUID


class OrderDraftConfirmation(OrderBase):
    draft_version: int = Field(ge=1, strict=True)
    confirmed: bool = Field(strict=True)

    items: list[OrderDraftItemConfirmation] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_confirmation(self) -> Self:
        if not self.confirmed:
            raise ValueError(
                "É necessária a confirmação explícita do pedido."
            )

        item_ids = [item.draft_item_id for item in self.items]

        if len(item_ids) != len(set(item_ids)):
            raise ValueError(
                "O mesmo item do rascunho não pode ser confirmado "
                "mais de uma vez."
            )

        return self

    def to_order_create(self) -> OrderCreate:
        return OrderCreate(
            buyer=self.buyer,
            conditions=self.conditions,
            delivery_start_date=self.delivery_start_date,
            delivery_end_date=self.delivery_end_date,
            items=[
                OrderItemCreate(
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit=item.unit,
                )
                for item in self.items
            ],
        )