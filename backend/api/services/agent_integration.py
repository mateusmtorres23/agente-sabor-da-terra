from collections.abc import Collection, Sequence
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from ..agents.config import PERNAMBUCO_TIMEZONE, to_pernambuco_date
from ..agents.consultation.schemas import (
    CitedSource,
    ConsultationResponse,
    ConsultationSourceItem,
    SourceKind,
)
from ..agents.schemas import (
    ConversationTurn,
    OrchestratorFlow,
    OrchestratorRequest,
    OrchestratorResponse,
)
from ..agents.triage.schemas import TriageAnalysis
from ..helpers.triage import format_triage_analysis
from ..models.chat_message import ChatMessage, ChatMessageFlow, ChatMessageRole
from ..models.document import Document, DocumentChunk
from ..models.solicitation import SolicitationType, SolicitationUrgency
from ..repositories.chat import (
    ChatRepository,
    normalize_message_reference_timestamp,
)
from ..schemas.agent_integration import (
    AgentConsultationResponsePayload,
    AgentPreparedResponse,
    AgentTriageResponsePayload,
    DocumentRetrievalContext,
    DocumentSourceProvider,
    PreparedTriageContext,
    RetrievedDocumentSources,
)


class AgentSessionNotFoundError(LookupError):
    """Sessão de conversa não encontrada no banco de dados."""


class SessionMessageMismatchError(ValueError):
    """Mensagens de outra sessão foram fornecidas ao montar o histórico."""


def _parse_optional_uuid(value: str | UUID | None) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        return UUID(cleaned)
    except ValueError:
        return None


def _parse_required_session_uuid(
    value: str | UUID,
    *,
    field_name: str,
    expected_session_id: UUID | None = None,
) -> UUID:
    parsed = _parse_optional_uuid(value)
    if parsed is None:
        raise ValueError(f"{field_name} must be a valid UUID, got {value!r}.")
    if expected_session_id is not None and parsed != expected_session_id:
        raise SessionMessageMismatchError(
            f"{field_name} targets session {parsed}, expected session {expected_session_id}."
        )
    return parsed


def _dedupe_sources(
    *collections: Sequence[ConsultationSourceItem] | None,
) -> list[ConsultationSourceItem]:
    ordered: list[ConsultationSourceItem] = []
    seen: set[str] = set()
    for collection in collections:
        if not collection:
            continue
        for item in collection:
            if item.source_id not in seen:
                seen.add(item.source_id)
                ordered.append(item)
    return ordered


def chat_message_role_to_turn_role(
    role: ChatMessageRole | str,
) -> Literal["user", "model"]:
    """Converte o papel persistido de ChatMessage para o papel de ConversationTurn."""
    if isinstance(role, ChatMessageRole):
        return "user" if role == ChatMessageRole.USER else "model"

    normalized = role.strip().upper()
    if normalized == "USER":
        return "user"
    if normalized in {"AGENT", "ASSISTANT", "MODEL"}:
        return "model"
    raise ValueError(f"Unsupported chat message role: {role!r}")


def chat_message_to_conversation_turn(message: ChatMessage) -> ConversationTurn:
    """Converte uma ChatMessage persistida em ConversationTurn sem presumir metadados ausentes."""
    flow_value: Literal["triage", "consultation"] | None = None
    if message.flow == ChatMessageFlow.TRIAGE.value:
        flow_value = "triage"
    elif message.flow == ChatMessageFlow.CONSULTATION.value:
        flow_value = "consultation"
    elif message.flow is not None:
        raise ValueError(f"Unsupported chat message flow: {message.flow!r}")

    return ConversationTurn(
        role=chat_message_role_to_turn_role(message.role),
        content=message.content,
        flow=flow_value,
        received_at=message.reference_received_at,
    )


def _sort_messages_for_history(messages: Sequence[ChatMessage]) -> list[ChatMessage]:
    return sorted(
        messages,
        key=lambda msg: (
            msg.position,
            msg.created_at,
            str(msg.id),
        ),
    )


def messages_to_conversation_turns(
    messages: Sequence[ChatMessage],
    *,
    session_id: UUID | None = None,
    exclude_message_id: UUID | None = None,
) -> list[ConversationTurn]:
    """Converte mensagens persistidas de uma sessão em histórico ordenado para o orquestrador."""
    ordered_messages = _sort_messages_for_history(messages)
    turns: list[ConversationTurn] = []
    for msg in ordered_messages:
        if session_id is not None and msg.session_id != session_id:
            raise SessionMessageMismatchError(
                f"Message {msg.id} belongs to session {msg.session_id}, "
                f"expected session {session_id}."
            )
        if exclude_message_id is not None and msg.id == exclude_message_id:
            continue
        turns.append(chat_message_to_conversation_turn(msg))
    return turns


def extract_triage_context_from_messages(
    messages: Sequence[ChatMessage],
    *,
    session_id: UUID | None = None,
) -> PreparedTriageContext:
    """Recupera a referência temporal da triagem persistida em chat_messages sem presumir nulos."""
    ordered = _sort_messages_for_history(messages)
    for msg in ordered:
        if session_id is not None and msg.session_id != session_id:
            raise SessionMessageMismatchError(
                f"Message {msg.id} belongs to session {msg.session_id}, "
                f"expected session {session_id}."
            )

    original_received_at: datetime | None = None
    for msg in reversed(ordered):
        if (
            msg.flow == ChatMessageFlow.TRIAGE.value
            and msg.reference_received_at is not None
        ):
            original_received_at = msg.reference_received_at
            break

    return PreparedTriageContext(
        original_received_at=original_received_at,
    )


def infer_source_kind(
    document_name: str,
    *,
    record_id: str | None = None,
    record_fields: dict[str, Any] | None = None,
) -> SourceKind:
    """Infere SourceKind coerente com o nome do arquivo e presença de registro estruturado."""
    basename = document_name.replace("\\", "/").rsplit("/", maxsplit=1)[-1].strip().lower()
    if basename == "financeiro.csv":
        return SourceKind.FINANCIAL_RECORD
    if basename == "lotes.csv":
        return SourceKind.LOT_RECORD
    if basename == "produtores.csv":
        return SourceKind.PRODUCER_RECORD
    if record_id or record_fields:
        return SourceKind.OTHER_RECORD
    return SourceKind.DOCUMENT_CHUNK


def document_chunk_to_source_item(
    chunk: DocumentChunk,
    *,
    document: Document | None = None,
    reference_label: str | None = None,
    source_kind: SourceKind | None = None,
) -> ConsultationSourceItem:
    """Converte um DocumentChunk persistido em ConsultationSourceItem preservando vínculos."""
    resolved_document = document if document is not None else chunk.document
    if resolved_document is None:
        raise ValueError(
            f"DocumentChunk {chunk.id} requires a loaded Document to build ConsultationSourceItem."
        )
    if resolved_document.id != chunk.document_id:
        raise ValueError(
            f"Document {resolved_document.id} does not match chunk.document_id {chunk.document_id}."
        )

    fields_copy = dict(chunk.record_fields) if chunk.record_fields is not None else None
    resolved_kind = source_kind or infer_source_kind(
        resolved_document.original_filename,
        record_id=chunk.record_id,
        record_fields=fields_copy,
    )
    return ConsultationSourceItem(
        source_id=str(chunk.id),
        source_kind=resolved_kind,
        document_id=str(resolved_document.id),
        document_name=resolved_document.original_filename,
        reference_label=reference_label if reference_label is not None else chunk.record_id,
        record_id=chunk.record_id,
        record_fields=fields_copy,
        content=chunk.content,
    )


def document_chunks_to_source_items(
    chunks: Sequence[DocumentChunk],
) -> list[ConsultationSourceItem]:
    """Converte uma sequência de DocumentChunks em ConsultationSourceItem sem duplicatas."""
    items: list[ConsultationSourceItem] = []
    seen_ids: set[UUID] = set()
    for chunk in chunks:
        if chunk.id in seen_ids:
            continue
        seen_ids.add(chunk.id)
        items.append(document_chunk_to_source_item(chunk))
    return items


def prepare_free_chat_request(
    *,
    session_id: UUID,
    message_text: str,
    persisted_messages: Sequence[ChatMessage],
    interaction_at: datetime | date | str | None = None,
    exclude_message_id: UUID | None = None,
    sources: Sequence[ConsultationSourceItem] = (),
    financial_records: Sequence[ConsultationSourceItem] | None = None,
    producer_id: str | None = None,
    period_start: datetime | date | str | None = None,
    period_end: datetime | date | str | None = None,
    financial_reference_date: datetime | date | str | None = None,
) -> OrchestratorRequest:
    """Monta OrchestratorRequest para chat livre a partir das mensagens persistidas no PostgreSQL."""
    history = messages_to_conversation_turns(
        persisted_messages,
        session_id=session_id,
        exclude_message_id=exclude_message_id,
    )
    resolved_interaction_at = (
        normalize_message_reference_timestamp(interaction_at)
        if interaction_at is not None
        else datetime.now(PERNAMBUCO_TIMEZONE)
    )
    return OrchestratorRequest(
        session_id=str(session_id),
        message_text=message_text,
        flow=OrchestratorFlow.AUTO,
        received_at=resolved_interaction_at,
        sources=list(sources),
        financial_records=(
            list(financial_records) if financial_records is not None else None
        ),
        producer_id=producer_id,
        period_start=period_start,
        period_end=period_end,
        financial_reference_date=financial_reference_date,
        history=history,
    )


def _resolve_triage_mode(
    *,
    explicit_flow: OrchestratorFlow | None,
    explicit_is_new: bool | None,
    history_length: int,
) -> tuple[bool, OrchestratorFlow]:
    is_new_triage = (
        explicit_is_new if explicit_is_new is not None else history_length == 0
    )
    resolved_flow = (
        explicit_flow
        if explicit_flow is not None
        else (OrchestratorFlow.TRIAGE if is_new_triage else OrchestratorFlow.AUTO)
    )
    return is_new_triage, resolved_flow


def prepare_triage_chat_request(
    *,
    session_id: UUID,
    message_text: str,
    persisted_messages: Sequence[ChatMessage],
    interaction_at: datetime | date | str | None = None,
    triage_context: PreparedTriageContext | None = None,
    flow: OrchestratorFlow | None = None,
    exclude_message_id: UUID | None = None,
    sources: Sequence[ConsultationSourceItem] = (),
    financial_records: Sequence[ConsultationSourceItem] | None = None,
) -> OrchestratorRequest:
    """Monta OrchestratorRequest para o chat da triagem distinguindo data original e data atual."""
    history = messages_to_conversation_turns(
        persisted_messages,
        session_id=session_id,
        exclude_message_id=exclude_message_id,
    )
    persisted_prior = [
        msg
        for msg in persisted_messages
        if exclude_message_id is None or msg.id != exclude_message_id
    ]
    recovered_context = extract_triage_context_from_messages(
        persisted_prior,
        session_id=session_id,
    )

    explicit = triage_context or PreparedTriageContext()
    original_received = (
        normalize_message_reference_timestamp(explicit.original_received_at)
        if explicit.original_received_at is not None
        else normalize_message_reference_timestamp(recovered_context.original_received_at)
    )
    resolved_interaction_at = (
        normalize_message_reference_timestamp(interaction_at)
        if interaction_at is not None
        else datetime.now(PERNAMBUCO_TIMEZONE)
    )

    is_new_triage, resolved_flow = _resolve_triage_mode(
        explicit_flow=flow,
        explicit_is_new=explicit.is_new_triage_message,
        history_length=len(history),
    )

    return OrchestratorRequest(
        session_id=str(session_id),
        message_text=message_text,
        flow=resolved_flow,
        received_at=resolved_interaction_at,
        message_received_at=original_received,
        is_new_triage_message=is_new_triage,
        sender=explicit.sender,
        buyer_name=explicit.buyer_name,
        channel=explicit.channel,
        source_id=explicit.source_id,
        sources=list(sources),
        financial_records=(
            list(financial_records) if financial_records is not None else None
        ),
        history=history,
    )


def convert_triage_analysis(analysis: TriageAnalysis) -> AgentTriageResponsePayload:
    """Converte TriageAnalysis para o formato da aplicação reaproveitando format_triage_analysis."""
    return AgentTriageResponsePayload(
        content=format_triage_analysis(analysis),
        summary=analysis.summary,
        request_type=SolicitationType(analysis.request_type.value),
        urgency=SolicitationUrgency(analysis.urgency.value),
        urgency_reason=analysis.urgency_reason,
        urgency_basis_action=analysis.urgency_basis_action,
        urgency_basis_date=analysis.urgency_basis_date,
        received_date_reference=analysis.received_date_reference,
        additional_intents=list(analysis.additional_intents),
        declared_urgency=analysis.declared_urgency,
        extracted_data=analysis.extracted_data,
        pending_items=list(analysis.pending_items),
        requires_clarification=analysis.requires_clarification,
        analysis=analysis,
    )


def convert_consultation_response(
    response: ConsultationResponse,
    *,
    provided_sources: Sequence[ConsultationSourceItem] = (),
) -> AgentConsultationResponsePayload:
    """Converte ConsultationResponse restringindo citações estritamente às fontes disponibilizadas."""
    provided_by_id = {src.source_id: src for src in provided_sources}
    excerpt_by_id = {
        cited.source_id: cited.supporting_excerpt
        for cited in response.cited_sources
        if cited.supporting_excerpt
    }

    claimed_ids: list[str] = []
    seen_claimed: set[str] = set()
    for sid in (*response.source_ids, *(c.source_id for c in response.cited_sources)):
        cleaned = sid.strip()
        if cleaned and cleaned not in seen_claimed:
            seen_claimed.add(cleaned)
            claimed_ids.append(cleaned)

    valid_source_ids: list[str] = []
    rejected_source_ids: list[str] = []
    citation_chunk_ids: list[UUID] = []
    seen_chunk_uuids: set[UUID] = set()
    rebuilt_cited: list[CitedSource] = []

    for sid in claimed_ids:
        src = provided_by_id.get(sid)
        if src is None:
            rejected_source_ids.append(sid)
            continue
        valid_source_ids.append(sid)
        rebuilt_cited.append(
            CitedSource(
                source_id=src.source_id,
                document_id=src.document_id,
                document_name=src.document_name,
                reference_label=src.reference_label,
                supporting_excerpt=excerpt_by_id.get(sid),
            )
        )
        parsed_uuid = _parse_optional_uuid(src.source_id)
        if parsed_uuid is not None and parsed_uuid not in seen_chunk_uuids:
            seen_chunk_uuids.add(parsed_uuid)
            citation_chunk_ids.append(parsed_uuid)

    return AgentConsultationResponsePayload(
        content=response.answer,
        reference_date_used=response.reference_date_used,
        has_sufficient_data=response.has_sufficient_data,
        source_ids=valid_source_ids,
        citation_chunk_ids=citation_chunk_ids,
        rejected_source_ids=rejected_source_ids,
        cited_sources=rebuilt_cited,
        gaps_and_divergences=list(response.gaps_and_divergences),
        response=response,
    )


def _resolve_triage_response_timestamp(
    analysis: TriageAnalysis,
    original_request: OrchestratorRequest | None,
) -> datetime:
    target_date = date.fromisoformat(analysis.received_date_reference)
    if original_request is not None:
        for candidate in (original_request.message_received_at, original_request.received_at):
            if candidate is None:
                continue
            normalized = normalize_message_reference_timestamp(candidate)
            if normalized is not None and to_pernambuco_date(normalized) == target_date:
                return normalized
    resolved = normalize_message_reference_timestamp(analysis.received_date_reference)
    assert resolved is not None
    return resolved


def convert_orchestrator_response(
    orchestrator_response: OrchestratorResponse,
    *,
    provided_sources: Sequence[ConsultationSourceItem] = (),
    original_request: OrchestratorRequest | None = None,
) -> AgentPreparedResponse:
    """Converte OrchestratorResponse para o contrato unificado da aplicação."""
    session_uuid = _parse_required_session_uuid(
        orchestrator_response.session_id,
        field_name="OrchestratorResponse.session_id",
    )
    if original_request is not None:
        _parse_required_session_uuid(
            original_request.session_id,
            field_name="OrchestratorRequest.session_id",
            expected_session_id=session_uuid,
        )

    effective_sources = _dedupe_sources(
        provided_sources,
        original_request.sources if original_request is not None else None,
        original_request.financial_records if original_request is not None else None,
    )
    provided_source_ids = [src.source_id for src in effective_sources]

    if isinstance(orchestrator_response.result, TriageAnalysis):
        if orchestrator_response.selected_flow != "triage":
            raise ValueError(
                "Inconsistent OrchestratorResponse: TriageAnalysis requires "
                "selected_flow='triage'."
            )
        triage_payload = convert_triage_analysis(orchestrator_response.result)
        ref_ts = _resolve_triage_response_timestamp(
            orchestrator_response.result,
            original_request,
        )
        return AgentPreparedResponse(
            session_id=session_uuid,
            selected_flow="triage",
            selected_agent="triage_agent",
            content=triage_payload.content,
            reference_received_at=ref_ts,
            citation_chunk_ids=[],
            provided_source_ids=provided_source_ids,
            rejected_source_ids=[],
            triage=triage_payload,
            consultation=None,
        )

    if orchestrator_response.selected_flow != "consultation":
        raise ValueError(
            "Inconsistent OrchestratorResponse: ConsultationResponse requires "
            "selected_flow='consultation'."
        )
    consultation_payload = convert_consultation_response(
        orchestrator_response.result,
        provided_sources=effective_sources,
    )
    ref_ts = normalize_message_reference_timestamp(
        consultation_payload.reference_date_used
    )
    return AgentPreparedResponse(
        session_id=session_uuid,
        selected_flow="consultation",
        selected_agent="consultation_agent",
        content=consultation_payload.content,
        reference_received_at=ref_ts,
        citation_chunk_ids=list(consultation_payload.citation_chunk_ids),
        provided_source_ids=provided_source_ids,
        rejected_source_ids=list(consultation_payload.rejected_source_ids),
        triage=None,
        consultation=consultation_payload,
    )


def _resolve_authorized_chunk_ids(
    prepared: AgentPreparedResponse,
    *,
    provided_sources: Sequence[ConsultationSourceItem] | None,
    allowed_chunk_ids: Collection[UUID] | None,
) -> set[UUID]:
    sets_to_intersect: list[set[UUID]] = []

    if provided_sources is not None:
        sets_to_intersect.append(
            {
                uid
                for src in provided_sources
                if (uid := _parse_optional_uuid(src.source_id)) is not None
            }
        )
    if allowed_chunk_ids is not None:
        sets_to_intersect.append(set(allowed_chunk_ids))

    if not sets_to_intersect:
        sets_to_intersect.append(
            {
                uid
                for sid in prepared.provided_source_ids
                if (uid := _parse_optional_uuid(sid)) is not None
            }
        )

    authorized = set(sets_to_intersect[0])
    for other in sets_to_intersect[1:]:
        authorized &= other
    return authorized


class AgentIntegrationService:
    """Serviço reutilizável de contratos, preparo de contexto e persistência para a #51 e #52."""

    def __init__(
        self,
        chat_repository: ChatRepository,
        *,
        source_provider: DocumentSourceProvider | None = None,
    ) -> None:
        self.chat_repository = chat_repository
        self.source_provider = source_provider

    async def load_session_history(
        self,
        session_id: UUID,
        *,
        exclude_message_id: UUID | None = None,
    ) -> list[ConversationTurn]:
        session = await self.chat_repository.get_session_by_id(session_id)
        if session is None:
            raise AgentSessionNotFoundError(f"Session {session_id} not found.")
        messages = await self.chat_repository.list_messages(session_id)
        return messages_to_conversation_turns(
            messages,
            session_id=session_id,
            exclude_message_id=exclude_message_id,
        )

    async def _resolve_sources_for_context(
        self,
        *,
        session_id: UUID,
        query_text: str,
        flow: OrchestratorFlow,
        reference_date: date | None,
        history: list[ConversationTurn],
        solicitation_id: UUID | None,
        sources: Sequence[ConsultationSourceItem] | None,
        financial_records: Sequence[ConsultationSourceItem] | None,
        producer_id: str | None = None,
        period_start: datetime | date | str | None = None,
        period_end: datetime | date | str | None = None,
        financial_reference_date: datetime | date | str | None = None,
    ) -> RetrievedDocumentSources:
        if sources is not None or financial_records is not None:
            return RetrievedDocumentSources(
                sources=list(sources or ()),
                financial_records=(
                    list(financial_records) if financial_records is not None else None
                ),
            )
        if self.source_provider is None:
            return RetrievedDocumentSources()
        return await self.source_provider.retrieve_sources(
            DocumentRetrievalContext(
                session_id=session_id,
                query_text=query_text,
                flow=flow,
                reference_date=reference_date,
                history=history,
                solicitation_id=solicitation_id,
                producer_id=producer_id,
                period_start=period_start,
                period_end=period_end,
                financial_reference_date=financial_reference_date,
            )
        )

    async def prepare_free_chat_input(
        self,
        session_id: UUID,
        message_text: str,
        *,
        interaction_at: datetime | date | str | None = None,
        exclude_message_id: UUID | None = None,
        sources: Sequence[ConsultationSourceItem] | None = None,
        financial_records: Sequence[ConsultationSourceItem] | None = None,
        producer_id: str | None = None,
        period_start: datetime | date | str | None = None,
        period_end: datetime | date | str | None = None,
        financial_reference_date: datetime | date | str | None = None,
    ) -> tuple[OrchestratorRequest, RetrievedDocumentSources]:
        """Prepara entrada do orquestrador para o chat livre a partir do PostgreSQL."""
        chat_session = await self.chat_repository.get_session_by_id(session_id)
        if chat_session is None:
            raise AgentSessionNotFoundError(f"Session {session_id} not found.")

        persisted = await self.chat_repository.list_messages(session_id)
        history = messages_to_conversation_turns(
            persisted,
            session_id=session_id,
            exclude_message_id=exclude_message_id,
        )
        resolved_interaction = (
            normalize_message_reference_timestamp(interaction_at)
            if interaction_at is not None
            else datetime.now(PERNAMBUCO_TIMEZONE)
        )
        assert resolved_interaction is not None
        retrieved = await self._resolve_sources_for_context(
            session_id=session_id,
            query_text=message_text,
            flow=OrchestratorFlow.AUTO,
            reference_date=to_pernambuco_date(resolved_interaction),
            history=history,
            solicitation_id=None,
            sources=sources,
            financial_records=financial_records,
            producer_id=producer_id,
            period_start=period_start,
            period_end=period_end,
            financial_reference_date=financial_reference_date,
        )
        request = prepare_free_chat_request(
            session_id=session_id,
            message_text=message_text,
            persisted_messages=persisted,
            interaction_at=resolved_interaction,
            exclude_message_id=exclude_message_id,
            sources=retrieved.sources,
            financial_records=retrieved.financial_records,
            producer_id=producer_id,
            period_start=period_start,
            period_end=period_end,
            financial_reference_date=financial_reference_date,
        )
        return request, retrieved

    async def prepare_triage_chat_input(
        self,
        session_id: UUID,
        message_text: str,
        *,
        interaction_at: datetime | date | str | None = None,
        triage_context: PreparedTriageContext | None = None,
        flow: OrchestratorFlow | None = None,
        exclude_message_id: UUID | None = None,
        sources: Sequence[ConsultationSourceItem] | None = None,
        financial_records: Sequence[ConsultationSourceItem] | None = None,
    ) -> tuple[OrchestratorRequest, RetrievedDocumentSources]:
        """Prepara entrada do orquestrador para o chat da triagem a partir do PostgreSQL."""
        chat_session = await self.chat_repository.get_session_by_id(session_id)
        if chat_session is None:
            raise AgentSessionNotFoundError(f"Session {session_id} not found.")

        persisted = await self.chat_repository.list_messages(session_id)
        history = messages_to_conversation_turns(
            persisted,
            session_id=session_id,
            exclude_message_id=exclude_message_id,
        )
        resolved_interaction = (
            normalize_message_reference_timestamp(interaction_at)
            if interaction_at is not None
            else datetime.now(PERNAMBUCO_TIMEZONE)
        )
        assert resolved_interaction is not None

        _, effective_flow = _resolve_triage_mode(
            explicit_flow=flow,
            explicit_is_new=(
                triage_context.is_new_triage_message
                if triage_context is not None
                else None
            ),
            history_length=len(history),
        )
        retrieved = await self._resolve_sources_for_context(
            session_id=session_id,
            query_text=message_text,
            flow=effective_flow,
            reference_date=to_pernambuco_date(resolved_interaction),
            history=history,
            solicitation_id=(
                triage_context.solicitation_id if triage_context is not None else None
            ),
            sources=sources,
            financial_records=financial_records,
        )
        request = prepare_triage_chat_request(
            session_id=session_id,
            message_text=message_text,
            persisted_messages=persisted,
            interaction_at=resolved_interaction,
            triage_context=triage_context,
            flow=flow,
            exclude_message_id=exclude_message_id,
            sources=retrieved.sources,
            financial_records=retrieved.financial_records,
        )
        return request, retrieved

    async def persist_agent_response(
        self,
        session_id: UUID,
        prepared: AgentPreparedResponse,
        *,
        provided_sources: Sequence[ConsultationSourceItem] | None = None,
        allowed_chunk_ids: Collection[UUID] | None = None,
        commit: bool = True,
    ) -> ChatMessage:
        """Persiste resposta do assistente e suas citações autorizadas na mesma transação."""
        if prepared.session_id != session_id:
            raise SessionMessageMismatchError(
                f"Prepared response targets session {prepared.session_id}, "
                f"expected session {session_id}."
            )

        chat_session = await self.chat_repository.get_session_by_id(session_id)
        if chat_session is None:
            raise AgentSessionNotFoundError(f"Session {session_id} not found.")

        authorized_chunk_ids = _resolve_authorized_chunk_ids(
            prepared,
            provided_sources=provided_sources,
            allowed_chunk_ids=allowed_chunk_ids,
        )
        filtered_chunk_ids = [
            cid
            for cid in prepared.citation_chunk_ids
            if cid in authorized_chunk_ids
        ]

        if not commit:
            async with self.chat_repository.session.begin_nested():
                return await self.chat_repository.add_message_with_citations(
                    session_id,
                    prepared.content,
                    role=ChatMessageRole.AGENT,
                    chunk_ids=filtered_chunk_ids,
                    flow=prepared.selected_flow,
                    reference_received_at=prepared.reference_received_at,
                )

        try:
            message = await self.chat_repository.add_message_with_citations(
                session_id,
                prepared.content,
                role=ChatMessageRole.AGENT,
                chunk_ids=filtered_chunk_ids,
                flow=prepared.selected_flow,
                reference_received_at=prepared.reference_received_at,
            )
            await self.chat_repository.session.commit()
        except Exception:
            await self.chat_repository.session.rollback()
            raise
        return message

    async def persist_orchestrator_response(
        self,
        session_id: UUID,
        orchestrator_response: OrchestratorResponse,
        *,
        provided_sources: Sequence[ConsultationSourceItem] = (),
        original_request: OrchestratorRequest | None = None,
        commit: bool = True,
    ) -> tuple[ChatMessage, AgentPreparedResponse]:
        """Converte OrchestratorResponse e persiste resposta + citações atomicamente."""
        _parse_required_session_uuid(
            orchestrator_response.session_id,
            field_name="OrchestratorResponse.session_id",
            expected_session_id=session_id,
        )
        if original_request is not None:
            _parse_required_session_uuid(
                original_request.session_id,
                field_name="OrchestratorRequest.session_id",
                expected_session_id=session_id,
            )

        effective_sources = _dedupe_sources(
            provided_sources,
            original_request.sources if original_request is not None else None,
            original_request.financial_records if original_request is not None else None,
        )
        prepared = convert_orchestrator_response(
            orchestrator_response,
            provided_sources=effective_sources,
            original_request=original_request,
        )
        message = await self.persist_agent_response(
            session_id,
            prepared,
            provided_sources=effective_sources,
            commit=commit,
        )
        return message, prepared
