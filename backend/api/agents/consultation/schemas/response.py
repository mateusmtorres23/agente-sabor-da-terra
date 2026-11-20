from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from .input import _normalize_iso_date_str


class CitedSource(BaseModel):
    source_id: str = Field(
        min_length=1,
        description="Identificador da fonte recuperada que sustenta a informação.",
    )
    document_id: str | None = Field(
        default=None,
        description="Identificador do documento original, quando disponível.",
    )
    document_name: str = Field(
        min_length=1,
        description="Nome do documento ou arquivo citado.",
    )
    reference_label: str | None = Field(
        default=None,
        description="Registro, lote, certificado ou seção pertinente dentro da fonte.",
    )
    supporting_excerpt: str | None = Field(
        default=None,
        description="Resumo ou trecho da evidência utilizada na resposta.",
    )

    @field_validator("source_id", mode="before")
    @classmethod
    def _coerce_cited_source_id(cls, value: Any) -> Any:
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("source_id must not be blank.")
            return cleaned
        return value

    @field_validator("document_id", mode="before")
    @classmethod
    def _coerce_cited_document_id(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value


class ConsultationGapOrDivergence(BaseModel):
    kind: Literal[
        "lacuna",
        "divergencia",
        "unidade_ambigua",
        "certificacao_vencida_ou_incompativel",
    ] = Field(
        description="Tipo de apontamento identificado nos dados consultados.",
    )
    description: str = Field(
        min_length=1,
        description="Explicação clara em português da lacuna, divergência ou pendência.",
    )
    source_ids: list[str] = Field(
        default_factory=list,
        description="Identificadores das fontes relacionadas ao apontamento.",
    )


class ConsultationResponse(BaseModel):
    answer: str = Field(
        min_length=1,
        description=(
            "Texto da resposta em português para exibição no chat, indicando a "
            "data de referência e as fontes."
        ),
    )
    reference_date_used: str = Field(
        description="Data de referência usada na análise no formato AAAA-MM-DD.",
    )
    source_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Lista ordenada e sem duplicatas dos identificadores (source_id) "
            "das fontes que sustentam a resposta."
        ),
    )
    cited_sources: list[CitedSource] = Field(
        default_factory=list,
        description="Detalhamento das fontes utilizadas na resposta.",
    )
    gaps_and_divergences: list[ConsultationGapOrDivergence] = Field(
        default_factory=list,
        description="Lacunas, divergências entre fontes, unidades ambíguas ou restrições.",
    )
    has_sufficient_data: bool = Field(
        default=True,
        description=(
            "False quando os trechos e registros fornecidos estão ausentes ou "
            "são insuficientes para responder à pergunta."
        ),
    )

    @field_validator("answer")
    @classmethod
    def _validate_answer(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("answer must not be blank.")
        return stripped

    @field_validator("reference_date_used", mode="before")
    @classmethod
    def _validate_reference_date_used(cls, value: date | datetime | str) -> str:
        normalized = _normalize_iso_date_str(value)
        if normalized is None:
            raise ValueError("reference_date_used is required.")
        return normalized

    @property
    def reference_date(self) -> date:
        return date.fromisoformat(self.reference_date_used)

    @model_validator(mode="after")
    def _deduplicate_and_sync_sources(self) -> "ConsultationResponse":
        ordered_ids: list[str] = []
        seen: set[str] = set()

        for sid in self.source_ids:
            cleaned = sid.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                ordered_ids.append(cleaned)

        for cited in self.cited_sources:
            cleaned = cited.source_id.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                ordered_ids.append(cleaned)

        self.source_ids = ordered_ids
        return self
