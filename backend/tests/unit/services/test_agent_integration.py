import json
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from google.genai import types
from pydantic import ValidationError

from api.agents import (
    ROUTER_OUTPUT_KEY,
    OrchestratorFlow,
    OrchestratorRequest,
    OrchestratorResponse,
    orchestrate_request,
)
from api.agents.config import PERNAMBUCO_TIMEZONE, to_pernambuco_date
from api.agents.consultation import (
    CONSULTATION_OUTPUT_KEY,
    CitedSource,
    ConsultationResponse,
    ConsultationSourceItem,
    SourceKind,
)
from api.agents.schemas import ConversationTurn
from api.agents.triage import TRIAGE_OUTPUT_KEY, TriageAnalysis
from api.models.chat_message import ChatMessage, ChatMessageFlow, ChatMessageRole
from api.models.document import Document, DocumentChunk
from api.models.solicitation import SolicitationType, SolicitationUrgency
from api.repositories.chat import normalize_message_reference_timestamp
from api.schemas.agent_integration import (
    AgentPreparedResponse,
    DocumentRetrievalContext,
    DocumentRetrievalError,
    InMemoryDocumentSourceProvider,
    PreparedTriageContext,
)
from api.schemas.chat import MessageCreate
from api.services.agent_integration import (
    SessionMessageMismatchError,
    chat_message_role_to_turn_role,
    chat_message_to_conversation_turn,
    convert_consultation_response,
    convert_orchestrator_response,
    convert_triage_analysis,
    document_chunk_to_source_item,
    document_chunks_to_source_items,
    extract_triage_context_from_messages,
    messages_to_conversation_turns,
    prepare_free_chat_request,
    prepare_triage_chat_request,
)


class _FakeSessionService:
    def __init__(self) -> None:
        self.sessions: dict[str, SimpleNamespace] = {}

    async def create_session(self, app_name: str, user_id: str) -> SimpleNamespace:
        session = SimpleNamespace(
            id=f"fake-session-{len(self.sessions) + 1}",
            app_name=app_name,
            user_id=user_id,
            state={},
        )
        self.sessions[session.id] = session
        return session

    async def get_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> SimpleNamespace | None:
        _ = (app_name, user_id)
        return self.sessions.get(session_id)


class _FakeAgentRunner:
    def __init__(self, state_key: str, payload: dict[str, Any]) -> None:
        self.app_name = f"fake_{state_key}"
        self.session_service = _FakeSessionService()
        self._state_key = state_key
        self._payload = payload
        self.received_prompts: list[str] = []

    async def run_async(
        self,
        user_id: str,
        session_id: str,
        new_message: types.Content,
    ) -> AsyncIterator[SimpleNamespace]:
        _ = user_id
        self.received_prompts.append(new_message.parts[0].text)
        session = self.session_service.sessions[session_id]
        session.state[self._state_key] = self._payload
        yield SimpleNamespace(
            content=types.Content(
                role="model",
                parts=[types.Part(text=json.dumps(self._payload, ensure_ascii=False))],
            ),
            is_final_response=lambda: True,
        )


def _make_chat_message(
    *,
    session_id: UUID,
    role: ChatMessageRole,
    content: str,
    position: int,
    flow: str | None = None,
    reference_received_at: datetime | None = None,
    created_at: datetime | None = None,
    message_id: UUID | None = None,
) -> ChatMessage:
    return ChatMessage(
        id=message_id or uuid4(),
        session_id=session_id,
        role=role,
        content=content,
        position=position,
        flow=flow,
        reference_received_at=reference_received_at,
        created_at=created_at or datetime(2026, 11, 1, 12, position, tzinfo=UTC),
    )


def test_message_create_aligns_blank_validation_with_conversation_turn() -> None:
    # Ponto 1 da revisão: MessageCreate e ConversationTurn rejeitam mensagens
    # vazias ou compostas exclusivamente por espaços.
    for blank in ("", " ", "   \n\t  "):
        with pytest.raises(ValidationError):
            MessageCreate(content=blank)
        with pytest.raises(ValidationError):
            ConversationTurn(role="user", content=blank)
        with pytest.raises(ValidationError):
            AgentPreparedResponse(
                session_id=uuid4(),
                selected_flow="consultation",
                selected_agent="consultation_agent",
                content=blank,
            )

    valid = MessageCreate(content="  Preciso consultar o lote LOT-2026-0094  ")
    assert valid.content == "Preciso consultar o lote LOT-2026-0094"
    turn = ConversationTurn(role="user", content=valid.content)
    assert turn.content == valid.content


def test_agent_contracts_accept_uuids_and_reject_invalid_types() -> None:
    session_uuid = uuid4()
    chunk_uuid = uuid4()
    doc_uuid = uuid4()
    origin_uuid = uuid4()

    turn = ConversationTurn(
        role="user",
        content="  Olá assistente  ",
        flow="triage",
        source_id=origin_uuid,  # type: ignore[arg-type]
    )
    assert turn.source_id == str(origin_uuid)
    assert turn.content == "Olá assistente"

    source = ConsultationSourceItem(
        source_id=chunk_uuid,  # type: ignore[arg-type]
        document_id=doc_uuid,  # type: ignore[arg-type]
        document_name="lotes.csv",
        record_id="LOT-2026-0094",
        content="lote_id=LOT-2026-0094; produto=alface",
    )
    assert source.source_id == str(chunk_uuid)
    assert source.document_id == str(doc_uuid)

    cited = CitedSource(
        source_id=chunk_uuid,  # type: ignore[arg-type]
        document_id=doc_uuid,  # type: ignore[arg-type]
        document_name="lotes.csv",
        reference_label="LOT-2026-0094",
    )
    assert cited.source_id == str(chunk_uuid)
    assert cited.document_id == str(doc_uuid)

    req = OrchestratorRequest(
        session_id=session_uuid,  # type: ignore[arg-type]
        message_text="Consultar lote LOT-2026-0094",
        source_id=origin_uuid,  # type: ignore[arg-type]
        sources=[source],
        history=[turn],
    )
    assert req.session_id == str(session_uuid)
    assert req.source_id == str(origin_uuid)

    resp = OrchestratorResponse(
        session_id=session_uuid,  # type: ignore[arg-type]
        selected_flow="consultation",
        selected_agent="consultation_agent",
        result=ConsultationResponse(
            answer="Lote LOT-2026-0094 consultado em 19/11/2026.",
            reference_date_used="2026-11-19",
            source_ids=[str(chunk_uuid)],
            cited_sources=[cited],
        ),
    )
    assert resp.session_id == str(session_uuid)

    with pytest.raises(ValidationError):
        OrchestratorRequest(session_id=None, message_text="Teste")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        OrchestratorRequest(session_id=12345, message_text="Teste")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ConsultationSourceItem(
            source_id=None,  # type: ignore[arg-type]
            document_name="doc.txt",
            content="Trecho",
        )


def test_normalize_reference_timestamp_preserves_pernambuco_calendar_day() -> None:
    bare_date = normalize_message_reference_timestamp(date(2026, 10, 28))
    iso_date_str = normalize_message_reference_timestamp("2026-10-28")
    aware_late_night = normalize_message_reference_timestamp("2026-10-28T23:30:00-03:00")
    utc_equivalent = normalize_message_reference_timestamp("2026-10-29T02:30:00Z")

    assert bare_date is not None and to_pernambuco_date(bare_date) == date(2026, 10, 28)
    assert iso_date_str is not None and to_pernambuco_date(iso_date_str) == date(2026, 10, 28)
    assert aware_late_night is not None and to_pernambuco_date(aware_late_night) == date(2026, 10, 28)
    assert utc_equivalent is not None and to_pernambuco_date(utc_equivalent) == date(2026, 10, 28)
    assert normalize_message_reference_timestamp(None) is None
    assert normalize_message_reference_timestamp("   ") is None


def test_messages_to_conversation_turns_preserves_order_roles_metadata_and_isolation() -> None:
    # Critérios 1, 2 e 5 da #50:
    # - ordena por position/created_at/id, converte USER->user e AGENT->model
    # - preserva metadados existentes e NÃO preenche metadados nulos de registros antigos
    # - exclui mensagem da interação atual (exclude_message_id) e bloqueia mistura de sessões
    session_id = uuid4()
    other_session_id = uuid4()
    current_msg_id = uuid4()
    ref_oct_28 = datetime(2026, 10, 28, 9, 30, tzinfo=PERNAMBUCO_TIMEZONE)

    msg_legacy = _make_chat_message(
        session_id=session_id,
        role=ChatMessageRole.USER,
        content="Mensagem legada sem metadados.",
        position=1,
        flow=None,
        reference_received_at=None,
    )
    msg_agent = _make_chat_message(
        session_id=session_id,
        role=ChatMessageRole.AGENT,
        content="Análise inicial da triagem.",
        position=2,
        flow=ChatMessageFlow.TRIAGE.value,
        reference_received_at=ref_oct_28,
    )
    msg_current = _make_chat_message(
        session_id=session_id,
        role=ChatMessageRole.USER,
        content="Esclarecimento atual que não deve duplicar no histórico.",
        position=3,
        message_id=current_msg_id,
    )

    # Passa propositalmente fora de ordem para confirmar ordenação determinística
    turns = messages_to_conversation_turns(
        [msg_current, msg_agent, msg_legacy],
        session_id=session_id,
        exclude_message_id=current_msg_id,
    )

    assert len(turns) == 2
    assert turns[0].role == "user"
    assert turns[0].content == "Mensagem legada sem metadados."
    assert turns[0].flow is None
    assert turns[0].received_at is None
    assert turns[0].source_id is None

    assert turns[1].role == "model"
    assert turns[1].content == "Análise inicial da triagem."
    assert turns[1].flow == "triage"
    assert turns[1].received_at == ref_oct_28
    assert turns[1].source_id is None

    # Rejeita mistura de sessões
    foreign_msg = _make_chat_message(
        session_id=other_session_id,
        role=ChatMessageRole.USER,
        content="Outra sessão",
        position=1,
    )
    with pytest.raises(SessionMessageMismatchError):
        messages_to_conversation_turns([msg_legacy, foreign_msg], session_id=session_id)

    assert chat_message_role_to_turn_role(ChatMessageRole.USER) == "user"
    assert chat_message_role_to_turn_role(ChatMessageRole.AGENT) == "model"
    assert chat_message_to_conversation_turn(msg_legacy).received_at is None


def test_prepare_triage_chat_request_distinguishes_october_receipt_from_november_interaction() -> None:
    # Critério 4 da #50: continuação de triagem iniciada em 28/10/2026 com interação em novembro
    # preserva a data original de recebimento e distingue a data da interação atual.
    session_id = uuid4()
    current_msg_id = uuid4()
    oct_28 = datetime(2026, 10, 28, 10, 15, tzinfo=PERNAMBUCO_TIMEZONE)
    nov_19 = datetime(2026, 11, 19, 15, 0, tzinfo=PERNAMBUCO_TIMEZONE)

    persisted = [
        _make_chat_message(
            session_id=session_id,
            role=ChatMessageRole.USER,
            content="Precisamos de queijo coalho para amanhã cedo.",
            position=1,
            flow=ChatMessageFlow.TRIAGE.value,
            reference_received_at=oct_28,
        ),
        _make_chat_message(
            session_id=session_id,
            role=ChatMessageRole.AGENT,
            content="Análise inicial da triagem: entrega prevista para 29/10/2026.",
            position=2,
            flow=ChatMessageFlow.TRIAGE.value,
            reference_received_at=oct_28,
        ),
        # Consulta intermediária em novembro NÃO pode sobrescrever a data original da triagem!
        _make_chat_message(
            session_id=session_id,
            role=ChatMessageRole.AGENT,
            content="Consulta documental em 19/11/2026.",
            position=3,
            flow=ChatMessageFlow.CONSULTATION.value,
            reference_received_at=nov_19,
        ),
        _make_chat_message(
            session_id=session_id,
            role=ChatMessageRole.USER,
            content="O cliente confirmou 30 kg de queijo coalho.",
            position=4,
            message_id=current_msg_id,
        ),
    ]

    recovered = extract_triage_context_from_messages(persisted[:-1], session_id=session_id)
    assert recovered.original_received_at == oct_28
    assert recovered.source_id is None
    assert recovered.sender is None
    assert recovered.channel is None

    # Metadados originais de recebimento (previstos em EntradaRecebida da #39) são
    # recebidos por parâmetro via PreparedTriageContext, enquanto a data original
    # (28/10/2026) é reconstruída automaticamente de chat_messages.reference_received_at.
    req = prepare_triage_chat_request(
        session_id=session_id,
        message_text="O cliente confirmou 30 kg de queijo coalho.",
        persisted_messages=persisted,
        interaction_at=nov_19,
        triage_context=PreparedTriageContext(
            source_id="PED-2026-003",
            sender="Supermercado Boa Vista",
            channel="whatsapp",
        ),
        exclude_message_id=current_msg_id,
    )

    assert req.session_id == str(session_id)
    assert req.is_new_triage_message is False
    assert req.message_received_at == oct_28
    assert to_pernambuco_date(req.message_received_at) == date(2026, 10, 28)
    assert req.received_at == nov_19
    assert to_pernambuco_date(req.received_at) == date(2026, 11, 19)
    assert req.source_id == "PED-2026-003"
    assert req.sender == "Supermercado Boa Vista"
    assert req.channel == "whatsapp"
    assert len(req.history) == 3
    assert all(
        turn.content != "O cliente confirmou 30 kg de queijo coalho."
        for turn in req.history
    )

    # Se houver nova triagem na mesma sessão, extract_triage_context_from_messages usa a referência mais recente
    second_triage = [
        _make_chat_message(
            session_id=session_id,
            role=ChatMessageRole.USER,
            content="Primeiro pedido antigo",
            position=1,
            flow=ChatMessageFlow.TRIAGE.value,
            reference_received_at=oct_28,
        ),
        _make_chat_message(
            session_id=session_id,
            role=ChatMessageRole.USER,
            content="Segundo pedido novo",
            position=2,
            flow=ChatMessageFlow.TRIAGE.value,
            reference_received_at=nov_19,
        ),
    ]
    latest_ctx = extract_triage_context_from_messages(second_triage, session_id=session_id)
    assert latest_ctx.original_received_at == nov_19

    # Também funciona para registro legado sem metadados quando PreparedTriageContext informa a origem (#39)
    legacy_msg = _make_chat_message(
        session_id=session_id,
        role=ChatMessageRole.USER,
        content="Mensagem original legada",
        position=1,
    )
    req_legacy = prepare_triage_chat_request(
        session_id=session_id,
        message_text="Esclarecimento em novembro",
        persisted_messages=[legacy_msg],
        interaction_at="2026-11-19",
        triage_context=PreparedTriageContext(
            original_received_at="2026-10-28",
            source_id="PED-2026-003",
        ),
    )
    assert req_legacy.history[0].received_at is None
    assert req_legacy.message_received_at is not None
    assert to_pernambuco_date(req_legacy.message_received_at) == date(2026, 10, 28)
    assert req_legacy.received_at is not None
    assert to_pernambuco_date(req_legacy.received_at) == date(2026, 11, 19)


def test_document_chunk_conversion_preserves_ids_metadata_and_source_kind() -> None:
    # Critério 8 da #50: trechos e registros documentais de teste são convertidos para
    # ConsultationSourceItem preservando identificadores e referências aos documentos originais.
    policy_doc = Document(
        id=uuid4(),
        original_filename="politica-comercial-2026.txt",
        storage_key="key-policy",
    )
    policy_chunk = DocumentChunk(
        id=uuid4(),
        document_id=policy_doc.id,
        content="Cláusula 4.2: prazo máximo de 48h úteis.",
        record_id=None,
        record_fields=None,
        document=policy_doc,
    )

    lotes_doc = Document(
        id=uuid4(),
        original_filename="lotes.csv",
        storage_key="key-lotes",
    )
    lote_chunk = DocumentChunk(
        id=uuid4(),
        document_id=lotes_doc.id,
        content="lote_id=LOT-2026-0094; produtor_id=P004; produto=alface; quantidade=300; unidade=unidades",
        record_id="LOT-2026-0094",
        record_fields={
            "lote_id": "LOT-2026-0094",
            "produtor_id": "P004",
            "produto": "alface",
            "quantidade": "300",
            "unidade": "unidades",
        },
        document=lotes_doc,
    )

    fin_doc = Document(
        id=uuid4(),
        original_filename="financeiro.csv",
        storage_key="key-fin",
    )
    fin_chunk = DocumentChunk(
        id=uuid4(),
        document_id=fin_doc.id,
        content="id_transacao=FIN-2026-006; produtor_id=P004; valor_total=750.00",
        record_id="FIN-2026-006",
        record_fields={"id_transacao": "FIN-2026-006", "produtor_id": "P004", "valor_total": "750.00"},
        document=fin_doc,
    )

    items = document_chunks_to_source_items([policy_chunk, lote_chunk, fin_chunk, lote_chunk])
    assert len(items) == 3

    policy_item, lote_item, fin_item = items
    assert policy_item.source_id == str(policy_chunk.id)
    assert policy_item.document_id == str(policy_doc.id)
    assert policy_item.document_name == "politica-comercial-2026.txt"
    assert policy_item.source_kind == SourceKind.DOCUMENT_CHUNK
    assert policy_item.record_id is None
    assert policy_item.record_fields is None

    assert lote_item.source_id == str(lote_chunk.id)
    assert lote_item.document_id == str(lotes_doc.id)
    assert lote_item.document_name == "lotes.csv"
    assert lote_item.source_kind == SourceKind.LOT_RECORD
    assert lote_item.record_id == "LOT-2026-0094"
    assert lote_item.reference_label == "LOT-2026-0094"
    assert lote_item.record_fields is not None
    assert lote_item.record_fields["unidade"] == "unidades"

    assert fin_item.source_kind == SourceKind.FINANCIAL_RECORD
    assert fin_item.record_id == "FIN-2026-006"

    # Rejeita DocumentChunk sem documento carregado ou com documento divergente
    detached_chunk = DocumentChunk(
        id=uuid4(),
        document_id=lotes_doc.id,
        content="sem doc",
        document=None,
    )
    with pytest.raises(ValueError, match="requires a loaded Document"):
        document_chunk_to_source_item(detached_chunk)
    with pytest.raises(ValueError, match="does not match"):
        document_chunk_to_source_item(lote_chunk, document=policy_doc)


def test_convert_triage_and_consultation_responses_preserve_structured_data_and_filter_sources() -> None:
    # Critérios 6, 7 e 10 da #50:
    # - TriageAnalysis preserva resumo, dados extraídos, prazos, urgência e pendências
    # - ConsultationResponse preserva conteúdo, data de referência e fontes autorizadas,
    #   rejeitando fontes que não foram disponibilizadas ao agente
    session_uuid = uuid4()

    triage_analysis = TriageAnalysis.model_validate(
        {
            "summary": "Pedido urgente de queijo coalho e mel com certificação orgânica.",
            "request_type": "pedido",
            "additional_intents": ["consulta de certificação"],
            "declared_urgency": False,
            "urgency": "urgente",
            "urgency_reason": "Entrega prevista para 29/10/2026.",
            "received_date_reference": "2026-10-28",
            "extracted_data": {
                "buyer_name": "Mercado Bom Preço",
                "buyer_contact": "compras@bompreco.example",
                "deadlines": [
                    {
                        "action": "entrega",
                        "date_start": "2026-10-29",
                        "reference_raw": "amanhã",
                    }
                ],
                "items": [
                    {
                        "product": "Queijo coalho",
                        "quantity": 10,
                        "unit": "kg",
                    },
                    {
                        "product": "Mel",
                        "quantity": None,
                        "unit": None,
                        "ambiguous_or_aggregate": True,
                        "clarification_needed": "Confirmar quantidade e unidade de mel.",
                    },
                ],
                "requirements": [
                    {
                        "description": "Certificado orgânico vigente",
                        "source": "mensagem",
                    }
                ],
                "requested_documents_or_sensitive_data": ["Certidão negativa"],
            },
            "pending_items": [],
        }
    )
    triage_payload = convert_triage_analysis(triage_analysis)
    assert triage_payload.summary == triage_analysis.summary
    assert triage_payload.request_type == SolicitationType.ORDER
    assert triage_payload.urgency == SolicitationUrgency.URGENT
    assert triage_payload.received_date_reference == "2026-10-28"
    assert len(triage_payload.extracted_data.items) == 2
    assert len(triage_payload.extracted_data.deadlines) == 1
    assert triage_payload.requires_clarification is True
    assert len(triage_payload.pending_items) >= 2
    assert "Análise inicial da triagem" in triage_payload.content
    assert "Prazo: 29/10/2026" in triage_payload.content
    assert "Queijo coalho: 10 kg" in triage_payload.content
    assert "Pendências:" in triage_payload.content

    allowed_chunk_id = uuid4()
    financial_chunk_id = uuid4()
    unprovided_chunk_id = uuid4()
    doc_id = uuid4()

    allowed_source = ConsultationSourceItem(
        source_id=str(allowed_chunk_id),
        document_id=str(doc_id),
        document_name="lotes.csv",
        record_id="LOT-2026-0094",
        content="lote_id=LOT-2026-0094; produtor_id=P004",
    )
    financial_source = ConsultationSourceItem(
        source_id=str(financial_chunk_id),
        source_kind=SourceKind.FINANCIAL_RECORD,
        document_id=str(doc_id),
        document_name="financeiro.csv",
        record_id="FIN-2026-006",
        content="id_transacao=FIN-2026-006; produtor_id=P004; valor_total=750.00",
    )

    simulated_consultation = ConsultationResponse(
        answer="Considerando 19/11/2026, o lote LOT-2026-0094 pertence a P004.",
        reference_date_used="2026-11-19",
        source_ids=[str(allowed_chunk_id), str(unprovided_chunk_id), "fake-id"],
        cited_sources=[
            CitedSource(
                source_id=str(allowed_chunk_id),
                document_name="nome-adulterado.txt",
                supporting_excerpt="Trecho relevante",
            ),
            CitedSource(
                source_id=str(unprovided_chunk_id),
                document_name="documento-nao-fornecido.txt",
            ),
        ],
        has_sufficient_data=True,
    )

    consult_payload = convert_consultation_response(
        simulated_consultation,
        provided_sources=[allowed_source],
    )
    assert consult_payload.content == simulated_consultation.answer
    assert consult_payload.reference_date_used == "2026-11-19"
    assert consult_payload.source_ids == [str(allowed_chunk_id)]
    assert consult_payload.citation_chunk_ids == [allowed_chunk_id]
    assert consult_payload.rejected_source_ids == [str(unprovided_chunk_id), "fake-id"]
    # Metadados de citação são reconstruídos a partir da fonte autoritativa disponibilizada
    assert len(consult_payload.cited_sources) == 1
    assert consult_payload.cited_sources[0].document_name == "lotes.csv"
    assert consult_payload.cited_sources[0].supporting_excerpt == "Trecho relevante"

    # Fontes provenientes de original_request.financial_records (#40) também são autorizadas
    fin_request = OrchestratorRequest(
        session_id=session_uuid,  # type: ignore[arg-type]
        message_text="Resumo financeiro de P004",
        sources=[allowed_source],
        financial_records=[financial_source],
    )
    fin_orch_resp = OrchestratorResponse(
        session_id=session_uuid,  # type: ignore[arg-type]
        selected_flow="consultation",
        selected_agent="consultation_agent",
        result=ConsultationResponse(
            answer="Resumo financeiro de P004: R$ 750,00 (FIN-2026-006).",
            reference_date_used="2026-09-30",
            source_ids=[str(financial_chunk_id), str(unprovided_chunk_id)],
        ),
    )
    prepared = convert_orchestrator_response(fin_orch_resp, original_request=fin_request)
    assert prepared.citation_chunk_ids == [financial_chunk_id]
    assert prepared.rejected_source_ids == [str(unprovided_chunk_id)]
    assert prepared.reference_received_at is not None
    assert to_pernambuco_date(prepared.reference_received_at) == date(2026, 9, 30)

    # Ponto 2 da revisão: original_request de outra sessão deve ser rejeitado
    other_session_request = OrchestratorRequest(
        session_id=uuid4(),  # type: ignore[arg-type]
        message_text="Resumo financeiro de outra sessão",
        sources=[allowed_source],
        financial_records=[financial_source],
    )
    with pytest.raises(SessionMessageMismatchError):
        convert_orchestrator_response(
            fin_orch_resp,
            original_request=other_session_request,
        )

    invalid_session_request = OrchestratorRequest(
        session_id="sessao-nao-uuid",
        message_text="Requisição com session_id inválido",
    )
    with pytest.raises(ValueError, match="OrchestratorRequest.session_id must be a valid UUID"):
        convert_orchestrator_response(
            fin_orch_resp,
            original_request=invalid_session_request,
        )

    # Inconsistência entre selected_flow e tipo de result é rejeitada
    with pytest.raises(ValueError, match="Inconsistent OrchestratorResponse"):
        convert_orchestrator_response(
            OrchestratorResponse(
                session_id=session_uuid,  # type: ignore[arg-type]
                selected_flow="consultation",
                selected_agent="consultation_agent",
                result=triage_analysis,
            )
        )


@pytest.mark.asyncio
async def test_prepared_requests_work_with_orchestrate_request_without_ai_or_ram_state() -> None:
    # Critérios 3, 4 e 12 da #50: demonstra execução completa dos contratos com
    # orchestrate_request() usando agentes simulados (sem modelo de IA e sem estado em RAM).
    session_id = uuid4()
    chunk_id = uuid4()
    doc_id = uuid4()
    oct_28 = datetime(2026, 10, 28, 8, 45, tzinfo=PERNAMBUCO_TIMEZONE)
    nov_19 = datetime(2026, 11, 19, 14, 0, tzinfo=PERNAMBUCO_TIMEZONE)

    persisted_triage = [
        _make_chat_message(
            session_id=session_id,
            role=ChatMessageRole.USER,
            content="Preciso de 20 kg de tomate para amanhã.",
            position=1,
            flow=ChatMessageFlow.TRIAGE.value,
            reference_received_at=oct_28,
        ),
        _make_chat_message(
            session_id=session_id,
            role=ChatMessageRole.AGENT,
            content="Análise inicial da triagem: prazo 29/10/2026.",
            position=2,
            flow=ChatMessageFlow.TRIAGE.value,
            reference_received_at=oct_28,
        ),
    ]

    triage_req = prepare_triage_chat_request(
        session_id=session_id,
        message_text="Comprador confirmou entrega na mesma data, pela manhã.",
        persisted_messages=persisted_triage,
        interaction_at=nov_19,
        triage_context=PreparedTriageContext(
            source_id="PED-2026-003",
            sender="Supermercado Boa Vista",
            channel="whatsapp",
        ),
        flow=OrchestratorFlow.TRIAGE,
    )
    fake_triage_runner = _FakeAgentRunner(
        TRIAGE_OUTPUT_KEY,
        {
            "summary": "Pedido confirmado de 20 kg de tomate para 29/10/2026 pela manhã.",
            "request_type": "pedido",
            "urgency": "urgente",
            "urgency_reason": "Entrega em 29/10/2026 (dia seguinte a 28/10/2026).",
            "received_date_reference": "2026-10-28",
            "extracted_data": {
                "delivery_date_start": "2026-10-29",
                "items": [{"product": "Tomate", "quantity": 20, "unit": "kg"}],
            },
            "pending_items": [],
        },
    )
    triage_resp = await orchestrate_request(
        triage_req,
        session_store=None,
        triage_runner=fake_triage_runner,
    )
    assert "data_recebimento_referencia: 2026-10-28" in fake_triage_runner.received_prompts[0]
    prepared_triage = convert_orchestrator_response(
        triage_resp,
        original_request=triage_req,
    )
    assert prepared_triage.selected_flow == "triage"
    assert prepared_triage.reference_received_at == oct_28
    assert prepared_triage.triage is not None
    assert prepared_triage.triage.urgency == SolicitationUrgency.URGENT

    # No chat livre (com InMemoryDocumentSourceProvider), consulta usa data atual (19/11/2026)
    source = ConsultationSourceItem(
        source_id=str(chunk_id),
        document_id=str(doc_id),
        document_name="politica-comercial-2026.txt",
        content="Prazo máximo de 48 horas úteis.",
    )
    provider = InMemoryDocumentSourceProvider(sources=[source])
    retrieved = await provider.retrieve_sources(
        DocumentRetrievalContext(
            session_id=session_id,
            query_text="Qual o prazo da política comercial?",
            reference_date=date(2026, 11, 19),
        )
    )
    free_req = prepare_free_chat_request(
        session_id=session_id,
        message_text="Qual o prazo da política comercial?",
        persisted_messages=[],
        interaction_at=nov_19,
        sources=retrieved.sources,
    )
    fake_router_runner = _FakeAgentRunner(
        ROUTER_OUTPUT_KEY,
        {"target_flow": "consultation", "reason": "Consulta documental."},
    )
    fake_consult_runner = _FakeAgentRunner(
        CONSULTATION_OUTPUT_KEY,
        {
            "answer": "Considerando 19/11/2026, o prazo máximo é de 48 horas úteis.",
            "reference_date_used": "2026-11-19",
            "source_ids": [str(chunk_id)],
            "cited_sources": [],
            "gaps_and_divergences": [],
            "has_sufficient_data": True,
        },
    )
    consult_resp = await orchestrate_request(
        free_req,
        session_store=None,
        router_runner=fake_router_runner,
        consultation_runner=fake_consult_runner,
    )
    assert "data_referencia: 2026-11-19" in fake_consult_runner.received_prompts[0]
    prepared_consult = convert_orchestrator_response(
        consult_resp,
        provided_sources=retrieved.all_provided_sources,
        original_request=free_req,
    )
    assert prepared_consult.citation_chunk_ids == [chunk_id]

    # Erro de recuperação documental é distinto de busca vazia (#50 / #52)
    empty_provider = InMemoryDocumentSourceProvider()
    empty_result = await empty_provider.retrieve_sources(
        DocumentRetrievalContext(
            session_id=session_id,
            query_text="Consulta sem fontes",
        )
    )
    assert empty_result.sources == []
    assert empty_result.financial_records is None
    assert issubclass(DocumentRetrievalError, RuntimeError)
