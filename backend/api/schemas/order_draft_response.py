from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .order import OrderResponse
from .order_draft import OrderDraftData


class OrderDraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    version: int
    data: OrderDraftData
    confirmed_order_id: UUID | None
    created_at: datetime


class OrderDraftContextResponse(BaseModel):
    draft: OrderDraftResponse | None
    order: OrderResponse | None
