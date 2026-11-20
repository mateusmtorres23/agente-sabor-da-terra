# Desenvolvimento

## Stack

- Frontend com React, TypeScript, React Router, Vite e npm. O Oxlint faz o lint. Os testes usam Vitest, React Testing Library e jsdom.
- Backend com Python 3.12 ou superior e uv. A API usa FastAPI e Pydantic. O acesso ao PostgreSQL usa SQLAlchemy assíncrono e asyncpg, com migrações pelo Alembic. A autenticação usa JWT e a API usa Argon2 para gerar hashes de senha. Pytest, Ruff e Testcontainers ficam no grupo `dev`. A camada de agentes usa Google ADK.

## Estrutura do repositório

```text
frontend/
  src/
    app/         # rotas da SPA
    components/  # componentes compartilhados
    features/    # páginas, componentes e lógica de cada funcionalidade
    lib/         # cliente HTTP e utilitários compartilhados
    styles/      # estilos globais e tokens visuais
  tests/
backend/
  api/
    app.py
    config.py
    database.py
    models/
    repositories/
    schemas/
    services/
    storage/
    routers/
    dependencies.py
    agents/
  alembic.ini
  alembic/
    versions/
  tests/
    unit/
    integration/
compose.yaml
```

Os routers recebem as requisições e delegam aos serviços. Os schemas definem a entrada e a saída da API. Os serviços aplicam as regras da aplicação e usam repositories para acessar o banco. Os repositories recebem uma sessão do SQLAlchemy e operam sobre os models. `dependencies.py` liga essas camadas e fornece `get_current_user` para as rotas internas que precisarem de autenticação. Use nomes em inglês no código, como `User` para a classe e `users` para a tabela.

A camada de agentes fica em `agents/`, com o orquestrador em `agent.py` e os agentes especializados em `triage/` e `consultation/`. A função assíncrona `orchestrate_request` é o ponto de entrada disponibilizado para integração com a aplicação. O objeto `root_agent` é mantido para compatibilidade com a CLI e a interface de desenvolvimento do Google ADK.

O orquestrador aceita o encaminhamento automático conforme a intenção da mensagem ou a indicação explícita do fluxo de triagem ou consulta documental. A integração dos agentes aos serviços de chat e ao processamento das mensagens recebidas será realizada nas entregas correspondentes.

O modelo padrão dos agentes é `gemini-3.8-flash`, podendo ser alterado pela variável `GEMINI_AGENT_MODEL`. Consulte a [documentação da camada de agentes](../backend/api/agents/README.md) para conhecer os contratos de entrada e retorno.

O serviço de documentos usa os adaptadores de `storage/` para gravar, abrir e excluir arquivos.

## Ambiente local

Suba uma instância local do PostgreSQL separadamente enquanto o Compose e os Dockerfiles estão em preparação.

| Variável | Uso |
| --- | --- |
| `DATABASE_URL` | Conexão do backend e do Alembic com o PostgreSQL, no formato `postgresql+asyncpg://usuario:senha@localhost:5432/banco`. |
| `JWT_SECRET_KEY` | Chave usada pela API para assinar e validar os tokens. |
| `CORS_ALLOWED_ORIGINS` | Origens da SPA aceitas pela API, separadas por vírgulas. Em desenvolvimento, use a origem aberta no navegador, como `http://localhost:5173`. |
| `DOCUMENT_STORAGE_BACKEND` | Armazenamento de documentos. Aceita `local` (padrão) ou `gcs`. |
| `DOCUMENT_STORAGE_DIR` | Diretório obrigatório no modo `local`. Caminhos relativos partem do diretório de execução da API. A primeira gravação cria o diretório se ele ainda estiver ausente. |
| `DOCUMENT_STORAGE_BUCKET` | Nome do bucket privado, obrigatório no modo `gcs`. |
| `DOCUMENT_UPLOAD_MAX_BYTES` | Limite do corpo multipart inteiro, em bytes. Aceita inteiros de 1 a 31.457.280. O padrão é 10.485.760 bytes (10 MiB). A API retorna HTTP `413` quando o corpo ultrapassa o limite. |
| `GEMINI_AGENT_MODEL` | Modelo utilizado pelos agentes. O padrão é `gemini-3.8-flash`. Quando definida, a variável não pode ter valor vazio. |
| `GOOGLE_GENAI_USE_ENTERPRISE` | Indicador de uso do ambiente Enterprise, reconhecido pela configuração dos agentes. |
| `GOOGLE_GENAI_USE_VERTEXAI` | Indicador de uso do Vertex AI, reconhecido pela configuração dos agentes. |
| `VITE_API_URL` | URL da API usada pela SPA. O padrão é `http://localhost:8000`. |

Em `backend/`, rode `uv sync`, aplique as migrações com `uv run alembic upgrade head` e suba a API com `uv run uvicorn api.app:app --reload`. Em `frontend/`, rode `npm ci` e `npm run dev`.

Para utilizar a interface de desenvolvimento do Google ADK, configure o acesso ao modelo e execute `uv run adk web api` em `backend/`.

A configuração das credenciais dos agentes depende da modalidade de acesso ao Gemini. A Gemini Developer API utiliza uma chave de API, enquanto o Vertex AI utiliza Application Default Credentials (ADC), que podem ser configuradas localmente com `gcloud auth application-default login`. Utilize as variáveis de ambiente correspondentes à modalidade escolhida, sem misturar suas configurações.

Não inclua credenciais ou segredos em arquivos versionados. Consulte a seção de configuração dos agentes em [Infraestrutura](infra.md#configuração-dos-agentes).

Quando um model mudar o esquema do banco, gere uma revisão em `backend/` com `uv run alembic revision --autogenerate -m "describe schema change"`. Confira as operações geradas, valide o `upgrade` e o `downgrade` em um banco descartável e inclua a migração no mesmo pull request do model.

## Verificações

- Em `backend/`, rode `uv run ruff check .` e `uv run pytest`. Os testes de integração que acessam PostgreSQL usam Testcontainers e precisam do Docker em execução.
- Para rodar apenas a regressão de documentos, execute `uv run pytest tests/integration/routers/test_document_flow.py` em `backend/` com o Docker em execução. O teste aplica as migrações em um banco descartável, obtém o JWT pela rota de login e verifica o fluxo com armazenamento local. Ao final, valida o downgrade e reaplica a migração.
- Em `frontend/`, rode `npm run lint`, `npm test` e `npm run build`. O build também verifica os tipos do TypeScript.

## Publicação

Na nuvem, o build estático da SPA será publicado no Firebase Hosting. A API e os agentes serão publicados juntos no Cloud Run e usarão o PostgreSQL do Cloud SQL e o bucket privado do Cloud Storage.

A imagem Docker do backend será construída localmente e armazenada no Artifact Registry. As migrações do Alembic serão executadas por meio do Cloud SQL Auth Proxy antes da publicação de uma nova revisão do backend, separadamente da inicialização dos contêineres.

O provisionamento, a publicação, as atualizações e o desprovisionamento serão automatizados por scripts Python utilizando as CLIs do Google Cloud e do Firebase. Os procedimentos de execução serão documentados junto aos scripts. Consulte [Infraestrutura](infra.md) para conhecer os serviços utilizados e as configurações do ambiente publicado.

## Entrega por funcionalidade

Organize o trabalho por fluxo de uso. A issue descreve o resultado esperado e os critérios de aceitação. O pull request reúne as mudanças necessárias para executar e verificar aquele fluxo, incluindo migração, API e interface quando fizerem parte da entrega.

O login foi a primeira entrega nesse formato. A migração cria `users`, `POST /auth/login` valida as credenciais e emite o JWT, e a tela abre `/chat` após o login. Para conferir o fluxo no navegador, cadastre um usuário de teste com `AuthService.hash_password()` e tente entrar com a senha correta e com a senha errada. A proteção de cada rota interna entra na entrega da funcionalidade que a usa. [US01](user-stories.md#us01---acessar-a-plataforma)