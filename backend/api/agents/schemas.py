from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from .consultation import ConsultationResponse, ConsultationSourceItem
from .triage import TriageAnalysis


def _coerce_optional_id_str(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return value


def _coerce_required_id_str(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field must not be blank.")
        return cleaned
    return value


class OrchestratorFlow(StrEnum):
    AUTO = "auto"
    TRIAGE = "triage"
    CONSULTATION = "consultation"


class IntentRouteDecision(BaseModel):
    target_flow: Literal["triage", "consultation"] = Field(
        description="Fluxo especialista escolhido para atender à mensagem no chat livre.",
    )
    reason: str = Field(
        min_length=1,
        description="Justificativa curta em português para o encaminhamento.",
    )


class ConversationTurn(BaseModel):
    role: Literal["user", "model"] = Field(
        description="Autor do turno na sessão ('user' para funcionário, 'model' para assistente).",
    )
    content: str = Field(
        min_length=1,
        description="Texto registrado no turno da conversa.",
    )
    flow: Literal["triage", "consultation"] | None = Field(
        default=None,
        description="Fluxo executado neste turno, quando conhecido.",
    )
    received_at: datetime | date | str | None = Field(
        default=None,
        description="Data/hora de recebimento associada à mensagem em análise neste turno.",
    )
    source_id: str | None = Field(
        default=None,
        description="Identificador externo da mensagem em análise neste turno, quando houver.",
    )

    @field_validator("source_id", mode="before")
    @classmethod
    def _coerce_source_id(cls, value: Any) -> Any:
        return _coerce_optional_id_str(value)

    @field_validator("content")
    @classmethod
    def _validate_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content must not be blank.")
        return stripped


class OrchestratorRequest(BaseModel):
    session_id: str = Field(
        min_length=1,
        description="Identificador único da sessão de conversa.",
    )
    message_text: str = Field(
        min_length=1,
        description="Mensagem enviada pelo funcionário no chat ou texto da tarefa da fila.",
    )
    flow: OrchestratorFlow = Field(
        default=OrchestratorFlow.AUTO,
        description=(
            "Fluxo a executar: 'auto' no chat livre ou 'triage'/'consultation' "
            "quando indicado pelo backend (ex.: fila de triagem)."
        ),
    )
    received_at: datetime | date | str | None = Field(
        default=None,
        description="Data/hora da mensagem ou da interação/consulta.",
    )
    message_received_at: datetime | date | str | None = Field(
        default=None,
        description=(
            "Data/hora original de recebimento da mensagem em análise quando "
            "informada separadamente da data da interação no chat."
        ),
    )
    is_new_triage_message: bool | None = Field(
        default=None,
        description=(
            "True quando o turno inicia a análise de uma nova mensagem recebida; "
            "False quando dá continuidade à triagem atual; None para detecção automática."
        ),
    )
    sender: str | None = Field(default=None)
    buyer_name: str | None = Field(default=None)
    channel: str | None = Field(default=None)
    source_id: str | None = Field(default=None)
    sources: list[ConsultationSourceItem] = Field(
        default_factory=list,
        description="Trechos e registros recuperados por busca para consulta documental.",
    )
    financial_records: list[ConsultationSourceItem] | None = Field(
        default=None,
        description=(
            "Coleção exaustiva de registros de financeiro.csv indexados no RAG para "
            "cálculos financeiros completos (independente da busca limitada por relevância)."
        ),
    )
    producer_id: str | None = Field(
        default=None,
        description="Identificador ou nome do produtor quando a solicitação envolve resumo financeiro.",
    )
    period_start: datetime | date | str | None = Field(
        default=None,
        description="Data inicial do período solicitado para resumo financeiro.",
    )
    period_end: datetime | date | str | None = Field(
        default=None,
        description="Data final do período solicitado para resumo financeiro.",
    )
    financial_reference_date: datetime | date | str | None = Field(
        default=None,
        description=(
            "Data de referência do cálculo financeiro quando distinta da data "
            "da interação (`received_at`)."
        ),
    )
    history: list[ConversationTurn] = Field(
        default_factory=list,
        description="Histórico anterior da sessão aberta, quando retomada.",
    )

    @field_validator("session_id", mode="before")
    @classmethod
    def _coerce_session_id(cls, value: Any) -> Any:
        return _coerce_required_id_str(value)

    @field_validator("source_id", mode="before")
    @classmethod
    def _coerce_optional_source_id(cls, value: Any) -> Any:
        return _coerce_optional_id_str(value)

    @field_validator("message_text")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field must not be blank.")
        return stripped


class OrchestratorResponse(BaseModel):
    session_id: str = Field(
        min_length=1,
        description="Identificador da sessão de conversa atendida.",
    )
    selected_flow: Literal["triage", "consultation"] = Field(
        description="Fluxo especialista que processou a solicitação.",
    )
    selected_agent: Literal["triage_agent", "consultation_agent"] = Field(
        description="Nome do agente especialista acionado.",
    )
    result: TriageAnalysis | ConsultationResponse = Field(
        description="Resultado estruturado no formato definido para o fluxo selecionado.",
    )
    session_history: list[ConversationTurn] = Field(
        default_factory=list,
        description="Histórico atualizado da sessão atual.",
    )

    @field_validator("session_id", mode="before")
    @classmethod
    def _coerce_response_session_id(cls, value: Any) -> Any:
        return _coerce_required_id_str(value)
