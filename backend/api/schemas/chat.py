from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from ..models.chat_message import ChatMessageRole
from .lot_draft import LotDraftOut, build_lot_draft_out


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class CitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: UUID
    chunk_id: UUID
    document_id: UUID
    document_name: str
    chunk_content: str
    record_id: str | None = None
    record_fields: dict[str, str] | None = None

    @computed_field
    @property
    def source_type(self) -> str:
        return "record" if self.record_id else "excerpt"

    @computed_field
    @property
    def label(self) -> str:
        if self.record_id:
            return f"{self.document_name} - {self.record_id}"
        return self.document_name

    @computed_field
    @property
    def view_url(self) -> str:
        return f"/documents/{self.document_id}/content"

    @computed_field
    @property
    def download_url(self) -> str:
        return f"/documents/{self.document_id}/download"

    @model_validator(mode="before")
    @classmethod
    def from_citation_orm(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return data
        chunk = data.chunk
        document = chunk.document
        return {
            "message_id": data.message_id,
            "chunk_id": data.chunk_id,
            "document_id": document.id,
            "document_name": document.original_filename,
            "chunk_content": chunk.content,
            "record_id": chunk.record_id,
            "record_fields": chunk.record_fields,
        }


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position: int
    role: str
    content: str
    created_at: datetime
    citations: list[CitationOut] = Field(default_factory=list)
    lot_draft: LotDraftOut | None = None

    @field_validator("role", mode="before")
    @classmethod
    def serialize_role(cls, role: str) -> str:
        return {ChatMessageRole.USER: "user", ChatMessageRole.AGENT: "assistant"}.get(
            role, role
        )

    @field_validator("lot_draft", mode="before")
    @classmethod
    def serialize_lot_draft(cls, value: Any) -> Any:
        if value is None or isinstance(value, (LotDraftOut, dict)):
            return value
        return build_lot_draft_out(value)


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    created_at: datetime


class SessionDetail(SessionOut):
    messages: list[MessageOut]