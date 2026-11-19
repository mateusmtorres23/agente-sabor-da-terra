from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..models.received_entry import ReceivedEntryStatus
from .solicitation import SolicitationOut


class ReceivedEntryIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    message_text: str = Field(min_length=1)
    sender: str = Field(min_length=1, max_length=255)
    source_channel: str = Field(min_length=1, max_length=100)
    received_at: datetime | None = None
    source_context: str | None = Field(default=None, max_length=255)
    external_id: str | None = Field(default=None, max_length=255)
    enqueue: bool = True


class ReceivedEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_text: str
    sender: str
    source_channel: str
    received_at: datetime
    triage_status: ReceivedEntryStatus
    failure_reason: str | None = None


class ReceivedEntryIngestResponse(BaseModel):
    entry: ReceivedEntryOut
    solicitation: SolicitationOut | None = None
    enqueued: bool


class TriageProcessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_token: UUID | None = None


class TriageRecoveryResponse(BaseModel):
    recovered_count: int
    entry_ids: list[UUID]