from collections.abc import Sequence
from datetime import date, datetime
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from ..agents.consultation.schemas import (
    CitedSource,
    ConsultationGapOrDivergence,
    ConsultationResponse,
    ConsultationSourceItem,
)
from ..agents.schemas import ConversationTurn, OrchestratorFlow
from ..agents.triage.schemas import (
    DeadlineAction,
    TriageAnalysis,
    TriageExtractedData,
    TriagePendingItem,
)
from ..models.solicitation import SolicitationType, SolicitationUrgency


class DocumentRetrievalError(RuntimeError):
    """Erro explícito na execução da busca documental (distinto de busca sem resultados)."""


class DocumentRetrievalContext(BaseModel):
    """Contexto enviado ao provedor de recuperação documental (#50 / #52)."""

    session_id: UUID = Field(
        description="Identificador da sessão de conversa em atendimento.",
    )
    query_text: str = Field(
        min_length=1,
        description="Mensagem atual do funcionário a ser atendida.",
    )
    flow: OrchestratorFlow = Field(
        default=OrchestratorFlow.AUTO,
        description="Fluxo previsto para a interação.",
    )
    reference_date: date | None = Field(
        default=None,
        description="Data de referência da interação atual no fuso de Pernambuco.",
    )
    history: list[ConversationTurn] = Field(
        default_factory=list,
        description="Histórico prévio da sessão para consultas de acompanhamento.",
    )
    solicitation_id: UUID | None = Field(
        default=None,
        description="Identificador da solicitação quando a sessão for de triagem.",
    )
    producer_id: str | None = Field(
        default=None,
        description="Identificador ou nome do produtor para recuperação financeira estruturada (#40 / #52).",
    )
    period_start: datetime | date | str | None = Field(
        default=None,
        description="Data inicial do período para filtros estruturados (#40 / #52).",
    )
    period_end: datetime | date | str | None = Field(
        default=None,
        description="Data final do período para filtros estruturados (#40 / #52).",
    )
    financial_reference_date: datetime | date | str | None = Field(
        default=None,
        description="Data de referência do cálculo financeiro quando distinta da data da interação.",
    )

    @field_validator("query_text")
    @classmethod
    def _strip_query_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query_text must not be blank.")
        return stripped


class RetrievedDocumentSources(BaseModel):
    """Fontes recuperadas e disponibilizadas ao agente em uma consulta (#50 / #52)."""

    sources: list[ConsultationSourceItem] = Field(
        default_factory=list,
        description="Trechos e registros recuperados por busca contextual.",
    )
    financial_records: list[ConsultationSourceItem] | None = Field(
        default=None,
        description=(
            "Coleção exaustiva de registros de financeiro.csv quando aplicável "
            "para cálculos determinísticos (#40)."
        ),
    )

    @property
    def all_provided_sources(self) -> list[ConsultationSourceItem]:
        ordered: list[ConsultationSourceItem] = []
        seen: set[str] = set()
        for item in (*self.sources, *(self.financial_records or [])):
            if item.source_id not in seen:
                seen.add(item.source_id)
                ordered.append(item)
        return ordered


@runtime_checkable
class DocumentSourceProvider(Protocol):
    """Contrato pelo qual o serviço de recuperação documental (#52) fornece fontes aos agentes."""

    async def retrieve_sources(
        self,
        context: DocumentRetrievalContext,
    ) -> RetrievedDocumentSources:
        ...


class InMemoryDocumentSourceProvider:
    """Provedor em memória para testes e validação sem busca vetorial/IA real."""

    def __init__(
        self,
        *,
        sources: Sequence[ConsultationSourceItem] = (),
        financial_records: Sequence[ConsultationSourceItem] | None = None,
    ) -> None:
        self._sources = list(sources)
        self._financial_records = (
            list(financial_records) if financial_records is not None else None
        )
        self.received_contexts: list[DocumentRetrievalContext] = []

    async def retrieve_sources(
        self,
        context: DocumentRetrievalContext,
    ) -> RetrievedDocumentSources:
        self.received_contexts.append(context)
        return RetrievedDocumentSources(
            sources=list(self._sources),
            financial_records=(
                list(self._financial_records)
                if self._financial_records is not None
                else None
            ),
        )


class PreparedTriageContext(BaseModel):
    """Metadados da mensagem original de triagem (#39 / #50 / #51)."""

    original_received_at: datetime | date | str | None = Field(
        default=None,
        description="Data/hora original de recebimento da mensagem triada.",
    )
    source_id: str | None = Field(
        default=None,
        description="Identificador externo ou UUID da entrada recebida.",
    )
    sender: str | None = Field(default=None)
    buyer_name: str | None = Field(default=None)
    channel: str | None = Field(default=None)
    solicitation_id: UUID | None = Field(default=None)
    is_new_triage_message: bool | None = Field(
        default=None,
        description=(
            "True para triagem inicial de nova mensagem; False para continuação; "
            "None para inferência conforme o histórico persistido."
        ),
    )

    @field_validator("source_id", mode="before")
    @classmethod
    def _coerce_source_id(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value


class AgentTriageResponsePayload(BaseModel):
    """Conversão de TriageAnalysis para uso pela aplicação preservando dados estruturados."""

    content: str = Field(
        min_length=1,
        description="Texto formatado da análise para exibição no chat da triagem.",
    )
    summary: str = Field(min_length=1)
    request_type: SolicitationType
    urgency: SolicitationUrgency
    urgency_reason: str = Field(min_length=1)
    urgency_basis_action: DeadlineAction | None = None
    urgency_basis_date: str | None = None
    received_date_reference: str = Field(min_length=1)
    additional_intents: list[str] = Field(default_factory=list)
    declared_urgency: bool = False
    extracted_data: TriageExtractedData
    pending_items: list[TriagePendingItem] = Field(default_factory=list)
    requires_clarification: bool = False
    analysis: TriageAnalysis

    @field_validator("content")
    @classmethod
    def _validate_content_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content must not be blank.")
        return stripped


class AgentConsultationResponsePayload(BaseModel):
    """Conversão de ConsultationResponse com citações restritas às fontes disponibilizadas."""

    content: str = Field(
        min_length=1,
        description="Texto da resposta de consulta documental para exibição no chat.",
    )
    reference_date_used: str = Field(min_length=1)
    has_sufficient_data: bool
    source_ids: list[str] = Field(
        default_factory=list,
        description="Identificadores citados validados contra as fontes disponibilizadas.",
    )
    citation_chunk_ids: list[UUID] = Field(
        default_factory=list,
        description="UUIDs de DocumentChunk prontos para persistência em citations.",
    )
    rejected_source_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Identificadores citados pela resposta que não pertenciam às fontes "
            "disponibilizadas ao agente (nunca persistidos)."
        ),
    )
    cited_sources: list[CitedSource] = Field(default_factory=list)
    gaps_and_divergences: list[ConsultationGapOrDivergence] = Field(
        default_factory=list
    )
    response: ConsultationResponse

    @field_validator("content")
    @classmethod
    def _validate_content_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content must not be blank.")
        return stripped


class AgentPreparedResponse(BaseModel):
    """Envelope unificado da resposta tratada do orquestrador pronta para persistência."""

    session_id: UUID
    selected_flow: Literal["triage", "consultation"]
    selected_agent: Literal["triage_agent", "consultation_agent"]
    content: str = Field(min_length=1)
    reference_received_at: datetime | None = None
    citation_chunk_ids: list[UUID] = Field(default_factory=list)
    provided_source_ids: list[str] = Field(default_factory=list)
    rejected_source_ids: list[str] = Field(default_factory=list)
    triage: AgentTriageResponsePayload | None = None
    consultation: AgentConsultationResponsePayload | None = None

    @field_validator("content")
    @classmethod
    def _validate_content_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content must not be blank.")
        return stripped
