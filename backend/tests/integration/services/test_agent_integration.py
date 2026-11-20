import json
from collections.abc import AsyncIterator
from datetime import date, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from google.genai import types
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api import database
from api.agents import (
    OrchestratorFlow,
    OrchestratorRequest,
    OrchestratorResponse,
    orchestrate_request,
)
from api.agents.config import PERNAMBUCO_TIMEZONE, to_pernambuco_date
from api.agents.consultation.schemas import (
    ConsultationResponse,
    ConsultationSourceItem,
)
from api.agents.triage import TRIAGE_OUTPUT_KEY
from api.app import fastapi_app as app
from api.database import get_db
from api.models.chat_message import ChatMessage, ChatMessageFlow, ChatMessageRole
from api.models.citation import Citation
from api.models.document import Document, DocumentChunk
from api.repositories.chat import ChatRepository
from api.repositories.document import DocumentRepository
from api.repositories.solicitation import SolicitationRepository
from api.repositories.user import UserRepository
from api.schemas.agent_integration import (
    AgentPreparedResponse,
    InMemoryDocumentSourceProvider,
    PreparedTriageContext,
)
from api.schemas.chat import MessageOut
from api.schemas.solicitation import SolicitationCreate
from api.services.agent_integration import (
    AgentIntegrationService,
    SessionMessageMismatchError,
    document_chunks_to_source_items,
)
from api.services.auth import AuthService
from api.services.solicitation import SolicitationService
from api.services.user import UserService

TEST_SECRET_KEY = "test-secret-key-with-at-least-32-bytes-long"


class _FakeSessionService:
    def __init__(self) -> None:
        self.sessions: dict[str, SimpleNamespace] = {}

    async def create_session(self, app_name: str, user_id: str) -> SimpleNamespace:
        session = SimpleNamespace(
            id=f"int-session-{len(self.sessions) + 1}",
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


class _FakeSpecialistRunner:
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


@pytest_asyncio.fixture(loop_scope="function")
async def api_client(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET_KEY)
    auth_sessions = async_sessionmaker(
        bind=await db_session.connection(),
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(database, "get_session_maker", lambda: auth_sessions)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def _create_user_and_token(db_session: AsyncSession) -> tuple[UUID, dict[str, str]]:
    user_repo = UserRepository(db_session)
    auth_service = AuthService(UserService(user_repo), secret_key=TEST_SECRET_KEY)
    user = await user_repo.create(
        f"agent-int-{uuid4()}@example.com",
        auth_service.hash_password("secret-pass"),
    )
    await db_session.commit()
    token = auth_service.create_access_token(user.id)
    return user.id, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_reconstructs_session_history_from_postgres_with_isolation_and_no_duplication(
    db_session: AsyncSession,
) -> None:
    # Critérios 1, 2 e 3 da #50: reconstrução fiel a partir do PostgreSQL sem estado em RAM,
    # mantendo isolamento entre sessões e sem duplicar a mensagem atual.
    user_id, _ = await _create_user_and_token(db_session)
    chat_repo = ChatRepository(db_session)
    session_a = await chat_repo.create_session(user_id)
    session_b = await chat_repo.create_session(user_id)

    await chat_repo.add_message(
        session_a.id,
        "Primeira pergunta na sessão A",
        role=ChatMessageRole.USER,
    )
    await chat_repo.add_message(
        session_a.id,
        "Resposta anterior na sessão A",
        role=ChatMessageRole.AGENT,
        flow=ChatMessageFlow.CONSULTATION,
        reference_received_at="2026-11-18",
    )
    current_user_msg = await chat_repo.add_message(
        session_a.id,
        "Pergunta da interação atual na sessão A",
        role=ChatMessageRole.USER,
    )
    await chat_repo.add_message(
        session_b.id,
        "Mensagem privada da sessão B que não pode vazar",
        role=ChatMessageRole.USER,
    )
    await db_session.commit()

    # Nova instância sem qualquer estado em memória
    service = AgentIntegrationService(ChatRepository(db_session))
    request, _ = await service.prepare_free_chat_input(
        session_a.id,
        current_user_msg.content,
        interaction_at="2026-11-19T15:30:00-03:00",
        exclude_message_id=current_user_msg.id,
    )

    assert request.session_id == str(session_a.id)
    assert request.flow == OrchestratorFlow.AUTO
    assert len(request.history) == 2
    assert [t.role for t in request.history] == ["user", "model"]
    assert [t.content for t in request.history] == [
        "Primeira pergunta na sessão A",
        "Resposta anterior na sessão A",
    ]
    assert request.history[0].flow is None
    assert request.history[0].received_at is None
    assert request.history[1].flow == "consultation"
    assert request.history[1].received_at is not None
    assert to_pernambuco_date(request.history[1].received_at) == date(2026, 11, 18)
    assert all("sessão B" not in t.content for t in request.history)


@pytest.mark.asyncio
async def test_triage_continuation_in_november_reconstructs_october_receipt_from_postgres(
    db_session: AsyncSession,
) -> None:
    # Critérios 3, 4 e 6 da #50:
    # Triagem criada em 28/10/2026 -> retomada em novembro via PostgreSQL sem estado em RAM ->
    # entrada preserva 28/10/2026 em message_received_at e distingue 19/11/2026 em received_at ->
    # retorno simulado de TriageAnalysis é convertido e persistido preservando os metadados.
    solicitation_service = SolicitationService(SolicitationRepository(db_session))
    solicitation = await solicitation_service.create_from_analysis(
        SolicitationCreate.model_validate(
            {
                "input": {
                    "message_text": "Precisamos de queijo coalho para amanhã cedo.",
                    "received_at": "2026-10-28T09:15:00-03:00",
                    "sender": "Supermercado Boa Vista",
                    "channel": "whatsapp",
                    "source_id": "PED-2026-003",
                },
                "analysis": {
                    "summary": "Pedido de queijo coalho para 29/10/2026 sem quantidade.",
                    "request_type": "pedido",
                    "urgency": "urgente",
                    "urgency_reason": "Entrega em 29/10/2026 (dia seguinte a 28/10/2026).",
                    "received_date_reference": "2026-10-28",
                    "extracted_data": {
                        "delivery_date_start": "2026-10-29",
                        "items": [
                            {
                                "product": "Queijo coalho",
                                "ambiguous_or_aggregate": True,
                                "clarification_needed": "Confirmar quantidade em kg.",
                            }
                        ],
                    },
                    "pending_items": [],
                },
            }
        )
    )

    staff_msg = await solicitation_service.add_message(
        solicitation.id,
        "O comprador confirmou 25 kg de queijo coalho mantendo o prazo.",
    )

    # Nova instância do serviço reconstrói o histórico e a data original (28/10/2026)
    # a partir do PostgreSQL, enquanto os metadados de origem (previstos em EntradaRecebida #39)
    # são informados por parâmetro via PreparedTriageContext.
    integration = AgentIntegrationService(ChatRepository(db_session))
    request, _ = await integration.prepare_triage_chat_input(
        solicitation.session_id,
        staff_msg.content,
        interaction_at="2026-11-19T16:00:00-03:00",
        triage_context=PreparedTriageContext(
            solicitation_id=solicitation.id,
            source_id="PED-2026-003",
            sender="Supermercado Boa Vista",
            channel="whatsapp",
        ),
        flow=OrchestratorFlow.TRIAGE,
        exclude_message_id=staff_msg.id,
    )

    assert request.message_received_at is not None
    assert to_pernambuco_date(request.message_received_at) == date(2026, 10, 28)
    assert request.received_at is not None
    assert to_pernambuco_date(request.received_at) == date(2026, 11, 19)
    assert request.is_new_triage_message is False
    assert request.source_id == "PED-2026-003"
    assert request.sender == "Supermercado Boa Vista"
    assert request.channel == "whatsapp"
    assert len(request.history) == 2

    fake_triage_runner = _FakeSpecialistRunner(
        TRIAGE_OUTPUT_KEY,
        {
            "summary": "Pedido de 25 kg de queijo coalho para entrega em 29/10/2026.",
            "request_type": "pedido",
            "urgency": "urgente",
            "urgency_reason": "Entrega em 29/10/2026.",
            "received_date_reference": "2026-10-28",
            "extracted_data": {
                "buyer_name": "Supermercado Boa Vista",
                "delivery_date_start": "2026-10-29",
                "items": [{"product": "Queijo coalho", "quantity": 25, "unit": "kg"}],
            },
            "pending_items": [],
        },
    )
    orch_response = await orchestrate_request(
        request,
        session_store=None,
        triage_runner=fake_triage_runner,
    )
    assert "data_recebimento_referencia: 2026-10-28" in fake_triage_runner.received_prompts[0]

    persisted_agent_msg, prepared = await integration.persist_orchestrator_response(
        solicitation.session_id,
        orch_response,
        original_request=request,
    )
    assert persisted_agent_msg.role == ChatMessageRole.AGENT
    assert persisted_agent_msg.flow == ChatMessageFlow.TRIAGE.value
    assert persisted_agent_msg.reference_received_at is not None
    assert to_pernambuco_date(persisted_agent_msg.reference_received_at) == date(2026, 10, 28)
    assert prepared.triage is not None
    assert prepared.triage.summary == "Pedido de 25 kg de queijo coalho para entrega em 29/10/2026."
    assert prepared.triage.extracted_data.items[0].quantity == 25
    assert "Queijo coalho: 25 kg" in persisted_agent_msg.content
    assert "Prazo: 29/10/2026" in persisted_agent_msg.content

    # Reconstrução subsequente a partir do banco mantém o histórico completo de 4 turnos
    reloaded_history = await integration.load_session_history(solicitation.session_id)
    assert len(reloaded_history) == 4
    assert [turn.role for turn in reloaded_history] == ["user", "model", "user", "model"]
    assert reloaded_history[-1].received_at is not None
    assert to_pernambuco_date(reloaded_history[-1].received_at) == date(2026, 10, 28)


@pytest.mark.asyncio
async def test_persists_consultation_response_with_only_provided_citations_and_retrieves_via_chat_api(
    db_session: AsyncSession,
    api_client: httpx.AsyncClient,
) -> None:
    # Critérios 7, 8, 9 e 10 da #50:
    # - converte DocumentChunks reais (trecho TXT + linha CSV) em ConsultationSourceItem
    # - persiste resposta simulada + citações na mesma transação
    # - NÃO persiste citação de chunk que existe no banco mas NÃO foi disponibilizado ao agente
    # - histórico e citações são recuperados normalmente pelo mecanismo existente (GET /chat/sessions/{id})
    user_id, headers = await _create_user_and_token(db_session)
    chat_repo = ChatRepository(db_session)
    doc_repo = DocumentRepository(db_session)

    session = await chat_repo.create_session(user_id)
    user_msg = await chat_repo.add_message(
        session.id,
        "O que diz o lote LOT-2026-0094 e a política comercial?",
        role=ChatMessageRole.USER,
    )

    policy_doc = Document(
        original_filename="politica-comercial-2026.txt",
        storage_key=f"test-policy-{uuid4().hex}",
    )
    lotes_doc = Document(
        original_filename="lotes.csv",
        storage_key=f"test-lotes-{uuid4().hex}",
    )
    secret_doc = Document(
        original_filename="documento-nao-disponibilizado.txt",
        storage_key=f"test-secret-{uuid4().hex}",
    )
    db_session.add_all([policy_doc, lotes_doc, secret_doc])
    await db_session.flush()

    policy_chunk = DocumentChunk(
        document_id=policy_doc.id,
        content="Cláusula 4.2: prazo máximo de 48h úteis.",
    )
    lote_chunk = DocumentChunk(
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
    )
    unprovided_chunk = DocumentChunk(
        document_id=secret_doc.id,
        content="Documento existente no banco mas não disponibilizado na consulta.",
    )
    db_session.add_all([policy_chunk, lote_chunk, unprovided_chunk])
    await db_session.commit()

    loaded_chunks = await doc_repo.list_chunks_by_ids([policy_chunk.id, lote_chunk.id])
    provided_sources = document_chunks_to_source_items(loaded_chunks)
    assert len(provided_sources) == 2

    source_provider = InMemoryDocumentSourceProvider(sources=provided_sources)
    integration = AgentIntegrationService(
        ChatRepository(db_session),
        source_provider=source_provider,
    )

    request, retrieved = await integration.prepare_free_chat_input(
        session.id,
        user_msg.content,
        interaction_at=datetime(2026, 11, 19, 10, 0, tzinfo=PERNAMBUCO_TIMEZONE),
        exclude_message_id=user_msg.id,
        producer_id="P004",
        period_start="2026-09-01",
        period_end="2026-09-30",
        financial_reference_date="2026-09-30",
    )
    assert len(source_provider.received_contexts) == 1
    assert source_provider.received_contexts[0].producer_id == "P004"
    assert source_provider.received_contexts[0].period_start == "2026-09-01"
    assert source_provider.received_contexts[0].period_end == "2026-09-30"
    assert source_provider.received_contexts[0].financial_reference_date == "2026-09-30"

    # Retorno simulado tenta citar 2 fontes disponibilizadas + 1 fonte NÃO disponibilizada
    simulated_orch_response = OrchestratorResponse(
        session_id=session.id,  # type: ignore[arg-type]
        selected_flow="consultation",
        selected_agent="consultation_agent",
        result=ConsultationResponse(
            answer=(
                "Em 19/11/2026, LOT-2026-0094 registra 300 unidades de alface (P004) e "
                "a política comercial prevê prazo máximo de 48h úteis."
            ),
            reference_date_used="2026-11-19",
            source_ids=[
                str(policy_chunk.id),
                str(lote_chunk.id),
                str(unprovided_chunk.id),
            ],
            has_sufficient_data=True,
        ),
    )

    persisted_msg, prepared = await integration.persist_orchestrator_response(
        session.id,
        simulated_orch_response,
        provided_sources=retrieved.all_provided_sources,
        original_request=request,
    )

    assert prepared.citation_chunk_ids == [policy_chunk.id, lote_chunk.id]
    assert prepared.rejected_source_ids == [str(unprovided_chunk.id)]
    assert {c.chunk_id for c in persisted_msg.citations} == {
        policy_chunk.id,
        lote_chunk.id,
    }
    assert MessageOut.model_validate(persisted_msg).role == "assistant"

    # Recuperação pelo endpoint existente de consulta ao histórico
    http_resp = await api_client.get(f"/chat/sessions/{session.id}", headers=headers)
    assert http_resp.status_code == 200
    body = http_resp.json()
    assert len(body["messages"]) == 2
    assistant_msg = body["messages"][1]
    assert assistant_msg["role"] == "assistant"
    cited_chunk_ids = {UUID(c["chunk_id"]) for c in assistant_msg["citations"]}
    assert cited_chunk_ids == {policy_chunk.id, lote_chunk.id}
    assert unprovided_chunk.id not in cited_chunk_ids

    csv_citation = next(
        c for c in assistant_msg["citations"] if UUID(c["chunk_id"]) == lote_chunk.id
    )
    assert csv_citation["source_type"] == "record"
    assert csv_citation["label"] == "lotes.csv - LOT-2026-0094"
    assert csv_citation["record_fields"]["unidade"] == "unidades"

    # Mesmo tentando burlar a conversão e passar chunk não disponibilizado diretamente,
    # persist_agent_response não grava citações não autorizadas
    forged = AgentPreparedResponse(
        session_id=session.id,
        selected_flow="consultation",
        selected_agent="consultation_agent",
        content="Tentativa com fonte não fornecida.",
        citation_chunk_ids=[unprovided_chunk.id],
        provided_source_ids=[],
    )
    forged_msg = await integration.persist_agent_response(
        session.id,
        forged,
        provided_sources=provided_sources,
    )
    assert forged_msg.citations == []
    unprovided_count = await db_session.scalar(
        select(func.count())
        .select_from(Citation)
        .where(Citation.chunk_id == unprovided_chunk.id)
    )
    assert unprovided_count == 0


@pytest.mark.asyncio
async def test_failed_citation_or_response_persistence_rolls_back_preserving_prior_history(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Critério 11 da #50: se a persistência da resposta ou de uma de suas citações falhar,
    # a transação é desfeita e preserva integralmente o histórico anterior.
    user_id, _ = await _create_user_and_token(db_session)
    chat_repo = ChatRepository(db_session)
    session = await chat_repo.create_session(user_id)
    prior_user_msg = await chat_repo.add_message(
        session.id,
        "Mensagem anterior que precisa permanecer intacta.",
        role=ChatMessageRole.USER,
    )

    doc = Document(
        original_filename="cert_p002.txt",
        storage_key=f"test-rollback-{uuid4().hex}",
    )
    db_session.add(doc)
    await db_session.flush()
    valid_chunk = DocumentChunk(
        document_id=doc.id,
        content="Certificado válido até 20/03/2027.",
    )
    db_session.add(valid_chunk)
    await db_session.commit()

    # Guarda os UUIDs antes do rollback (rollback expira instâncias ORM na AsyncSession)
    session_id = session.id
    prior_user_msg_id = prior_user_msg.id
    doc_id = doc.id
    valid_chunk_id = valid_chunk.id
    valid_chunk_content = valid_chunk.content

    # Caso 1: falha de FK na 2ª citação (chunk ausente no banco) desfaz mensagem + 1ª citação
    missing_chunk_id = uuid4()
    valid_source = ConsultationSourceItem(
        source_id=str(valid_chunk_id),
        document_id=str(doc_id),
        document_name="cert_p002.txt",
        content=valid_chunk_content,
    )
    stale_source = ConsultationSourceItem(
        source_id=str(missing_chunk_id),
        document_id=str(doc_id),
        document_name="cert_p002.txt",
        content="Chunk obsoleto removido do banco.",
    )

    integration = AgentIntegrationService(ChatRepository(db_session))
    failing_prepared = AgentPreparedResponse(
        session_id=session_id,
        selected_flow="consultation",
        selected_agent="consultation_agent",
        content="Resposta cuja 2ª citação falhará por integridade referencial.",
        citation_chunk_ids=[valid_chunk_id, missing_chunk_id],
        provided_source_ids=[valid_source.source_id, stale_source.source_id],
    )

    with pytest.raises(IntegrityError):
        await integration.persist_agent_response(
            session_id,
            failing_prepared,
            provided_sources=[valid_source, stale_source],
        )

    messages_after_fk_fail = await ChatRepository(db_session).list_messages(session_id)
    assert [m.id for m in messages_after_fk_fail] == [prior_user_msg_id]
    citation_count = await db_session.scalar(
        select(func.count()).select_from(Citation)
    )
    assert citation_count == 0

    # Caso 2: falha simulada no meio de add_citation também desfaz toda a operação
    original_add_citation = ChatRepository.add_citation

    async def failing_add_citation(
        self: ChatRepository,
        message_id: UUID,
        chunk_id: UUID,
    ) -> Citation:
        await original_add_citation(self, message_id, chunk_id)
        raise RuntimeError("falha simulada ao gravar citação")

    monkeypatch.setattr(ChatRepository, "add_citation", failing_add_citation)

    failing_runtime_prepared = AgentPreparedResponse(
        session_id=session_id,
        selected_flow="consultation",
        selected_agent="consultation_agent",
        content="Resposta que falha ao gravar citação.",
        citation_chunk_ids=[valid_chunk_id],
        provided_source_ids=[valid_source.source_id],
    )

    with pytest.raises(RuntimeError, match="falha simulada ao gravar citação"):
        await integration.persist_agent_response(
            session_id,
            failing_runtime_prepared,
            provided_sources=[valid_source],
        )

    messages_after_runtime_fail = await ChatRepository(db_session).list_messages(session_id)
    assert [m.id for m in messages_after_runtime_fail] == [prior_user_msg_id]
    citation_count_after = await db_session.scalar(
        select(func.count()).select_from(Citation)
    )
    assert citation_count_after == 0

    # Caso 3: modo composable (commit=False / savepoint) desfaz apenas o savepoint sem perder o histórico anterior
    with pytest.raises(RuntimeError, match="falha simulada ao gravar citação"):
        await integration.persist_agent_response(
            session_id,
            failing_runtime_prepared,
            provided_sources=[valid_source],
            commit=False,
        )

    messages_after_savepoint_fail = await ChatRepository(db_session).list_messages(session_id)
    assert [m.id for m in messages_after_savepoint_fail] == [prior_user_msg_id]

    # Caso 4: falha na persistência da própria resposta (add_message) também preserva o histórico anterior
    monkeypatch.setattr(ChatRepository, "add_citation", original_add_citation)
    original_add_message = ChatRepository.add_message

    async def failing_add_message(
        self: ChatRepository,
        *args: Any,
        **kwargs: Any,
    ) -> ChatMessage:
        await original_add_message(self, *args, **kwargs)
        raise RuntimeError("falha simulada ao gravar resposta")

    monkeypatch.setattr(ChatRepository, "add_message", failing_add_message)
    with pytest.raises(RuntimeError, match="falha simulada ao gravar resposta"):
        await integration.persist_agent_response(
            session_id,
            failing_runtime_prepared,
            provided_sources=[valid_source],
        )

    messages_after_response_fail = await ChatRepository(db_session).list_messages(session_id)
    assert [m.id for m in messages_after_response_fail] == [prior_user_msg_id]
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.session_id == session_id)
        )
        == 1
    )


@pytest.mark.asyncio
async def test_whitespace_only_messages_are_rejected_across_chat_and_solicitation_endpoints(
    db_session: AsyncSession,
    api_client: httpx.AsyncClient,
) -> None:
    # Ponto 1 da revisão: impede o cadastro de mensagens compostas apenas por espaços
    # tanto no chat livre quanto no chat da triagem e no repositório, garantindo que o
    # histórico persistido seja sempre reconstruível como ConversationTurn.
    _, headers = await _create_user_and_token(db_session)

    created_session = await api_client.post("/chat/sessions", headers=headers)
    assert created_session.status_code == 201
    session_id = UUID(created_session.json()["id"])

    for blank in ("", " ", "   \n\t  "):
        chat_resp = await api_client.post(
            f"/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"content": blank},
        )
        assert chat_resp.status_code == 422

    # Mensagem válida com espaços nas pontas é normalizada e reconstruível sem erro
    ok_resp = await api_client.post(
        f"/chat/sessions/{session_id}/messages",
        headers=headers,
        json={"content": "   Qual o prazo da política comercial?   "},
    )
    assert ok_resp.status_code == 201
    assert ok_resp.json()["content"] == "Qual o prazo da política comercial?"

    history = await AgentIntegrationService(ChatRepository(db_session)).load_session_history(
        session_id
    )
    assert len(history) == 1
    assert history[0].content == "Qual o prazo da política comercial?"

    # Também rejeita mensagens compostas só por espaços no chat da triagem e no repositório
    solicitation_service = SolicitationService(SolicitationRepository(db_session))
    solicitation = await solicitation_service.create_from_analysis(
        SolicitationCreate.model_validate(
            {
                "input": {
                    "message_text": "Pedido de teste para validação de espaços.",
                    "received_at": "2026-10-28T09:00:00-03:00",
                    "source_id": "PED-BLANK-1",
                },
                "analysis": {
                    "summary": "Pedido de teste.",
                    "request_type": "pedido",
                    "urgency": "normal",
                    "urgency_reason": "Prazo regular.",
                    "received_date_reference": "2026-10-28",
                    "extracted_data": {},
                    "pending_items": [],
                },
            }
        )
    )
    triage_resp = await api_client.post(
        f"/solicitations/{solicitation.id}/messages",
        headers=headers,
        json={"content": "   \t  "},
    )
    assert triage_resp.status_code == 422

    with pytest.raises(ValueError, match="must not be blank"):
        await ChatRepository(db_session).add_message(session_id, "   \n  ")


@pytest.mark.asyncio
async def test_persist_orchestrator_response_rejects_mismatched_sessions_without_persisting(
    db_session: AsyncSession,
) -> None:
    # Ponto 2 da revisão: original_request, orchestrator_response e session_id devem
    # corresponder à mesma sessão; qualquer combinação incompatível é rejeitada sem gravar dados.
    user_id, _ = await _create_user_and_token(db_session)
    chat_repo = ChatRepository(db_session)
    session_a = await chat_repo.create_session(user_id)
    session_b = await chat_repo.create_session(user_id)

    doc = Document(
        original_filename="politica-comercial-2026.txt",
        storage_key=f"test-mismatch-{uuid4().hex}",
    )
    db_session.add(doc)
    await db_session.flush()
    chunk = DocumentChunk(
        document_id=doc.id,
        content="Prazo de 48 horas úteis.",
    )
    db_session.add(chunk)
    await db_session.commit()

    session_a_id = session_a.id
    session_b_id = session_b.id
    source = ConsultationSourceItem(
        source_id=str(chunk.id),
        document_id=str(doc.id),
        document_name="politica-comercial-2026.txt",
        content=chunk.content,
    )

    request_a = OrchestratorRequest(
        session_id=session_a_id,  # type: ignore[arg-type]
        message_text="Qual o prazo na sessão A?",
        sources=[source],
    )
    request_b = OrchestratorRequest(
        session_id=session_b_id,  # type: ignore[arg-type]
        message_text="Qual o prazo na sessão B?",
        sources=[source],
    )
    response_a = OrchestratorResponse(
        session_id=session_a_id,  # type: ignore[arg-type]
        selected_flow="consultation",
        selected_agent="consultation_agent",
        result=ConsultationResponse(
            answer="Prazo de 48 horas úteis.",
            reference_date_used="2026-11-19",
            source_ids=[str(chunk.id)],
            has_sufficient_data=True,
        ),
    )
    response_b = OrchestratorResponse(
        session_id=session_b_id,  # type: ignore[arg-type]
        selected_flow="consultation",
        selected_agent="consultation_agent",
        result=ConsultationResponse(
            answer="Prazo de 48 horas úteis.",
            reference_date_used="2026-11-19",
            source_ids=[str(chunk.id)],
            has_sufficient_data=True,
        ),
    )

    integration = AgentIntegrationService(ChatRepository(db_session))

    # Combinação 1: original_request de B com response de A e destino A
    with pytest.raises(SessionMessageMismatchError):
        await integration.persist_orchestrator_response(
            session_a_id,
            response_a,
            original_request=request_b,
        )

    # Combinação 2: response de B com original_request de A e destino A
    with pytest.raises(SessionMessageMismatchError):
        await integration.persist_orchestrator_response(
            session_a_id,
            response_b,
            original_request=request_a,
        )

    # Combinação 3: destino B com original_request e response de A
    with pytest.raises(SessionMessageMismatchError):
        await integration.persist_orchestrator_response(
            session_b_id,
            response_a,
            original_request=request_a,
        )

    assert await ChatRepository(db_session).list_messages(session_a_id) == []
    assert await ChatRepository(db_session).list_messages(session_b_id) == []
    citation_count = await db_session.scalar(
        select(func.count()).select_from(Citation)
    )
    assert citation_count == 0
