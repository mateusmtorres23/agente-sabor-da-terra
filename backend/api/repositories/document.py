from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.chat_message import ChatMessage
from ..models.chat_session import ChatSession
from ..models.citation import Citation
from ..models.document import Document, DocumentChunk


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, original_filename: str, storage_key: str) -> Document:
        document = Document(original_filename=original_filename, storage_key=storage_key)
        self.session.add(document)
        await self.session.flush()
        return document

    async def list_all(self) -> list[Document]:
        statement = select(Document).order_by(Document.original_filename, Document.id)
        result = await self.session.scalars(statement)
        return list(result)

    async def get_by_id(self, document_id: UUID) -> Document | None:
        return await self.session.get(Document, document_id)

    async def list_chunks_by_ids(
        self, chunk_ids: Sequence[UUID]
    ) -> list[DocumentChunk]:
        if not chunk_ids:
            return []
        statement = (
            select(DocumentChunk)
            .where(DocumentChunk.id.in_(list(chunk_ids)))
            .options(selectinload(DocumentChunk.document))
        )
        chunks_by_id = {
            chunk.id: chunk for chunk in (await self.session.scalars(statement)).all()
        }
        ordered: list[DocumentChunk] = []
        seen: set[UUID] = set()
        for cid in chunk_ids:
            if cid in chunks_by_id and cid not in seen:
                seen.add(cid)
                ordered.append(chunks_by_id[cid])
        return ordered

    async def list_citations_by_document(
        self, document_id: UUID
    ) -> list[tuple[Citation, DocumentChunk, ChatMessage, ChatSession]]:
        statement = (
            select(Citation, DocumentChunk, ChatMessage, ChatSession)
            .join(DocumentChunk, Citation.chunk_id == DocumentChunk.id)
            .join(ChatMessage, Citation.message_id == ChatMessage.id)
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .where(DocumentChunk.document_id == document_id)
            .order_by(ChatMessage.created_at.asc())
        )
        result = await self.session.execute(statement)
        return list(result.all())

    async def delete(self, document: Document) -> None:
        await self.session.delete(document)
        await self.session.flush()