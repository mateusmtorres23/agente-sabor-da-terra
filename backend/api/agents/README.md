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