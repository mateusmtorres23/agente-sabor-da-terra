# Camada de Agentes (`api.agents`)

Este pacote implementa a camada multiagente da Cooperativa Sabor da Terra com Google ADK.

## Configuração do modelo

O modelo padrão dos agentes é `gemini-3.8-flash`, definido em `config.py`. O modelo pode ser substituído pela variável de ambiente `GEMINI_AGENT_MODEL`, que não pode ter valor vazio quando definida.

São consideradas duas modalidades de acesso aos modelos Gemini:

- **Gemini Developer API:** utiliza uma chave de API.
- **Vertex AI:** utiliza Application Default Credentials (ADC).

As variáveis `GOOGLE_GENAI_USE_ENTERPRISE` e `GOOGLE_GENAI_USE_VERTEXAI` são reconhecidas pela configuração dos agentes para identificar o uso do ambiente Enterprise ou Vertex AI.

Configure as credenciais e as variáveis de ambiente correspondentes à modalidade escolhida. Não inclua chaves de API ou outras credenciais em arquivos versionados.

No ambiente publicado, a modalidade de acesso e o modelo serão definidos durante o provisionamento, considerando disponibilidade, cotas, custos e privacidade dos dados. Consulte a seção [Configuração dos agentes](../../../docs/infra.md#configuração-dos-agentes) da documentação de infraestrutura.

## Ponto de Entrada da Aplicação

A função assíncrona **`orchestrate_request`** é o ponto de entrada oficial disponibilizado pela camada de agentes para integração com os serviços de chat e de processamento da triagem. A integração com esses serviços ainda será implementada.

- **Caminho de importação principal:**
  ```python
  from api.agents.agent import orchestrate_request
  # ou
  from api.agents import orchestrate_request
  ```
- **`root_agent` (`api.agents.agent.root_agent`):**
  Mantido em `api/agents/agent.py` exclusivamente para compatibilidade com a CLI e a interface de desenvolvimento do Google ADK (`uv run adk web api`).

## Contratos de Entrada e Retorno

### Entrada: `OrchestratorRequest` (`api.agents.schemas.OrchestratorRequest`)

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `session_id` | `str` | Identificador único da sessão de conversa. |
| `message_text` | `str` | Texto enviado pelo funcionário no chat ou mensagem da fila de triagem. |
| `flow` | `OrchestratorFlow` (`"auto"`, `"triage"`, `"consultation"`) | `"auto"` (padrão) usa o classificador semântico no chat livre com fallback heurístico; `"triage"` e `"consultation"` acionam diretamente o especialista indicado pelo backend. |
| `received_at` | `datetime \| date \| str \| None` | Data/hora da mensagem ou da interação/consulta. Na continuação de uma triagem em andamento, a data da mensagem em análise é preservada; ao iniciar a análise de uma nova mensagem na mesma sessão, a referência temporal é atualizada para a nova mensagem. |
| `message_received_at` | `datetime \| date \| str \| None` | Data/hora original de recebimento da mensagem em análise quando informada separadamente da data da interação no chat. |
| `is_new_triage_message` | `bool \| None` | Indica explicitamente se o turno inicia uma nova análise (`True`) ou continua a análise atual (`False`); quando `None`, o orquestrador detecta automaticamente por `source_id`, `message_received_at` ou intenção do texto. |
| `sender`, `buyer_name`, `channel`, `source_id` | `str \| None` | Metadados opcionais do canal de entrada para a triagem. |
| `sources` | `list[ConsultationSourceItem]` | Trechos documentais (`DocumentChunk`) e registros recuperados por busca para consultas documentais. |
| `financial_records` | `list[ConsultationSourceItem] \| None` | Coleção exaustiva de registros de `financeiro.csv` indexados no RAG para resumos financeiros (alternativa ou complemento ao parâmetro `financial_records_provider` de `orchestrate_request`). |
| `producer_id`, `period_start`, `period_end`, `financial_reference_date` | `str \| date \| datetime \| None` | Parâmetros opcionais de produtor, período e data de referência do cálculo financeiro (também extraíveis de consultas em linguagem natural, distintos da data da interação). |
| `history` | `list[ConversationTurn]` | Histórico prévio da sessão aberta, enviado em bloco separado do texto da mensagem em análise. |

### Retorno: `OrchestratorResponse` (`api.agents.schemas.OrchestratorResponse`)

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `session_id` | `str` | Identificador da sessão atendida. |
| `selected_flow` | `Literal["triage", "consultation"]` | Fluxo especialista que processou a solicitação. |
| `selected_agent` | `Literal["triage_agent", "consultation_agent"]` | Nome do agente especialista acionado. |
| `result` | `TriageAnalysis \| ConsultationResponse` | Saída estruturada e validada do especialista (`TriageAnalysis` em `api.agents.triage.schemas` ou `ConsultationResponse` em `api.agents.consultation.schemas`). |
| `session_history` | `list[ConversationTurn]` | Histórico atualizado da sessão atual (preservando `received_at` e `flow` por turno). |

## Camada de Integração com a Aplicação (`#50`)

Os componentes de compatibilização, reconstrução de contexto persistido, conversão de retornos e persistência transacional ficam em:

- **Contratos e protocolos:** `api.schemas.agent_integration`
- **Conversores e serviço reutilizável:** `api.services.agent_integration` (`AgentIntegrationService`)
- **Injeção FastAPI:** `api.dependencies.get_agent_integration_service`

### 1. Metadados conversacionais persistidos em `chat_messages`

Para reconstruir o contexto da conversa a partir do PostgreSQL sem depender do estado em memória (`OrchestratorSessionStore`), `ChatMessage` persiste as seguintes colunas opcionais (mantidas `NULL` para registros legados):

| Coluna | Tipo | Finalidade |
| --- | --- | --- |
| `flow` | `VARCHAR(32)` (`'triage'` \| `'consultation'` \| `NULL`) | Fluxo executado no turno. |
| `reference_received_at` | `TIMESTAMPTZ` (`NULL`) | Referência temporal do turno (data original de recebimento na triagem ou data de referência da consulta). |

- Os metadados originais de recebimento (`source_id`, `sender`, `buyer_name`, `channel`) pertencem à modelagem de `EntradaRecebida` (`#39`) e são repassados por parâmetro via `PreparedTriageContext` (sem depender da conclusão da `#39`).
- As citações possuem persistência própria na tabela `citations`, enquanto os retornos estruturados completos (`TriageAnalysis` e `ConsultationResponse`) são preservados em memória no envelope `AgentPreparedResponse` para consumo pelos serviços da `#51`.
- Mensagens vazias ou compostas apenas por espaços são rejeitadas tanto em `MessageCreate` quanto em `ChatRepository.add_message`, mantendo alinhamento com `ConversationTurn`.

### 2. Contrato de fornecimento de fontes documentais (RAG `#52`)

O serviço de recuperação documental implementa o protocolo `DocumentSourceProvider`:

```python
from api.schemas.agent_integration import (
    DocumentRetrievalContext,
    DocumentRetrievalError,
    DocumentSourceProvider,
    RetrievedDocumentSources,
)
from api.services.agent_integration import document_chunks_to_source_items


class RagDocumentSourceProvider(DocumentSourceProvider):
    async def retrieve_sources(
        self,
        context: DocumentRetrievalContext,
    ) -> RetrievedDocumentSources:
        try:
            chunks = ...  # DocumentChunk com relationship `.document` carregado
            financial_chunks = ...  # Coleção exaustiva de financeiro.csv quando aplicável
        except Exception as exc:
            raise DocumentRetrievalError("Falha na consulta documental.") from exc
        return RetrievedDocumentSources(
            sources=document_chunks_to_source_items(chunks),
            financial_records=document_chunks_to_source_items(financial_chunks),
        )
```

Cada `DocumentChunk` convertido por `document_chunk_to_source_item()` preserva `source_id = str(chunk.id)`, `document_id = str(chunk.document_id)`, `document_name = chunk.document.original_filename`, `record_id`, `record_fields` e `source_kind`. Uma busca sem resultados retorna `RetrievedDocumentSources(sources=[], financial_records=None)`, enquanto erros de execução devem sinalizar `DocumentRetrievalError`.

### 3. Exemplo de uso pelos serviços de chat (`#51`)

#### Chat livre

```python
from api.agents import orchestrate_request
from api.repositories.chat import ChatRepository
from api.services.agent_integration import AgentIntegrationService

integration = AgentIntegrationService(
    ChatRepository(db_session),
    source_provider=source_provider,
)

# 1. Prepara OrchestratorRequest reconstruindo o histórico do PostgreSQL
#    (exclude_message_id evita duplicar a mensagem atual se já tiver sido gravada)
request, retrieved = await integration.prepare_free_chat_input(
    session_id=chat.id,
    message_text=user_text,
    interaction_at=now_pe,
    exclude_message_id=user_message.id,
)

# 2. Executa o orquestrador sem depender de estado em memória
orchestrator_response = await orchestrate_request(request)

# 3. Converte o retorno e persiste resposta + citações autorizadas na mesma transação
agent_message, prepared = await integration.persist_orchestrator_response(
    session_id=chat.id,
    orchestrator_response=orchestrator_response,
    provided_sources=retrieved.all_provided_sources,
    original_request=request,
)
```

#### Continuação no chat da triagem

```python
from api.schemas.agent_integration import PreparedTriageContext

request, retrieved = await integration.prepare_triage_chat_input(
    session_id=solicitation.session_id,
    message_text=clarification_text,
    interaction_at="2026-11-19T14:00:00-03:00",
    # A data original (ex.: 28/10/2026) é recuperada automaticamente de
    # chat_messages.reference_received_at; metadados de origem (ex.: EntradaRecebida da #39)
    # são informados por parâmetro via PreparedTriageContext.
    triage_context=PreparedTriageContext(
        solicitation_id=solicitation.id,
        source_id="PED-2026-003",
        sender="Supermercado Boa Vista",
        channel="whatsapp",
    ),
    exclude_message_id=user_message.id,
)
# request.message_received_at preserva 2026-10-28; request.received_at registra 2026-11-19.
```

- `convert_orchestrator_response()` e `persist_orchestrator_response()` validam que `original_request`, `orchestrator_response` e `session_id` pertencem à mesma sessão antes de autorizar fontes ou persistir dados.
- Para compor a persistência da resposta do assistente com a atualização do cartão de `Solicitation` na mesma transação (prevista na `#51`), passe `commit=False` a `persist_agent_response()` / `persist_orchestrator_response()`.
- Citações cuja fonte (`chunk_id`) não tenha sido disponibilizada ao agente na consulta são descartadas em `rejected_source_ids` e nunca são persistidas em `citations`.
- Qualquer falha na gravação da mensagem ou de uma citação desfaz a transação, preservando intacto o histórico anterior.
