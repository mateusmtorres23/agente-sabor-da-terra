# Infraestrutura

A aplicação usa o Google Cloud. O Firebase Hosting publica a interface React. Um serviço do Cloud Run executa a API FastAPI, o orquestrador e os agentes de triagem e consulta implementados com Google ADK. O Cloud SQL persiste as mensagens recebidas, e o Cloud Tasks limita a carga das triagens para que o mesmo serviço possa atender ao chat.

Os recursos serão provisionados em um único projeto Google Cloud dedicado à aplicação, ao qual o Firebase também será associado.

Os recursos regionais da demonstração ficarão em Iowa (`us-central1`). A região tem tarifas de Tier 1 no Cloud Run e dá acesso à franquia do Cloud Storage. O Cloud Run, o Cloud SQL, o Artifact Registry e o bucket ficarão na mesma região para evitar transferências entre regiões. [Preços do Cloud Run](https://cloud.google.com/run/pricing) · [Franquia do Cloud Storage](https://cloud.google.com/storage/pricing#cloud-storage-always-free-usage-limits)

![System design da aplicação](assets/system-design.svg)

## Explicação dos serviços

#### Google Cloud Run

O Cloud Run hospeda a API FastAPI e os agentes no mesmo serviço. A API atende ao frontend, recebe as mensagens dos canais integrados e do script Facepe e atende às chamadas autenticadas do Cloud Tasks e do Cloud Scheduler.

A API persiste a entrada no Cloud SQL antes de confirmar o recebimento ao canal e solicita o enfileiramento no Cloud Tasks. Quando a tarefa é disparada, a API recupera o texto e a data de recebimento originais, chama o agente e grava o resultado da triagem.

Escolhemos o Cloud Run porque a carga é pequena e varia ao longo do dia. O serviço ajusta o número de instâncias automaticamente e pode reduzir a zero em períodos sem tráfego. Isso evita manter um servidor ativo só para aguardar mensagens. [Escalonamento do Cloud Run](https://docs.cloud.google.com/run/docs/about-instance-autoscaling)

A configuração inicial será:

| Parâmetro | Configuração |
| --- | --- |
| Ambiente de execução | Primeira geração |
| CPU | 1 vCPU |
| Memória | 512 MiB |
| Workers do Uvicorn | 1 por instância |
| Instâncias mínimas | 0 |
| Instâncias máximas | 2 |
| Concorrência | 10 requisições por instância |
| Timeout | 300 segundos |
| Modalidade de cobrança | Por requisição |

O dimensionamento poderá ser ajustado conforme os resultados dos testes, considerando o consumo dos agentes e a capacidade do banco de dados.

O serviço disponibilizará um endpoint HTTPS público para permitir o acesso pelo frontend. A autenticação e a autorização das requisições serão realizadas pela aplicação.

#### Artifact Registry

O Artifact Registry armazena as imagens Docker do backend em um repositório privado na região `us-central1`. As imagens são construídas localmente, versionadas pelo hash do commit Git e utilizadas na publicação de novas revisões do Cloud Run. A publicação utiliza o digest da imagem para identificar precisamente o artefato implantado.

Escolhemos o serviço pela integração nativa com o Cloud Run e pela possibilidade de armazenar e gerenciar as imagens em um repositório privado, sem depender de um serviço externo. [Artifact Registry](https://docs.cloud.google.com/artifact-registry/docs/overview)

#### Firebase Hosting

O Firebase Hosting publica os arquivos gerados pelo build do React. Escolhemos o serviço porque o frontend é estático e o Firebase simplifica a publicação, disponibilizando HTTPS e CDN para distribuir esses arquivos.

Será utilizado o site padrão do projeto Firebase, com os domínios fornecidos pelo serviço, sem necessidade de configurar um domínio personalizado.

A variável `VITE_API_URL` será configurada durante o build do frontend com a URL do serviço Cloud Run. O backend utilizará `CORS_ALLOWED_ORIGINS` para restringir as origens permitidas aos domínios utilizados pela aplicação. [Firebase Hosting](https://firebase.google.com/docs/hosting)

#### Cloud SQL

O Cloud SQL hospeda o PostgreSQL com os usuários, as conversas, os pedidos, as entradas de mensagens e os dados usados na consulta documental. Cada `EntradaRecebida` guarda o UUID, o texto original, o remetente, o canal de origem, a data de recebimento e o estado da triagem. O UUID identifica reentregas. O agente de consulta usa a extensão `pgvector` para buscar trechos que ajudam a responder às perguntas. [Modelo do banco](schemas-db.md) · [Busca vetorial no Cloud SQL](https://docs.cloud.google.com/sql/docs/postgres/ai-overview)

A configuração inicial da instância será:

| Parâmetro | Configuração |
| --- | --- |
| Versão do PostgreSQL | 16 |
| Edição | Enterprise |
| Tipo de máquina | `db-f1-micro` |
| Disponibilidade | Zonal |
| Armazenamento | 10 GiB SSD |
| Aumento automático do armazenamento | Desabilitado |
| Réplicas | Nenhuma |
| Backups automáticos | Desabilitados |
| Recuperação para um ponto no tempo (PITR) | Desabilitada |

A configuração foi escolhida considerando a carga reduzida e o caráter temporário do ambiente. A ausência de backups automáticos e PITR implica que não há garantia de recuperação dos dados em caso de perda.

A conexão do Cloud Run com o banco será realizada pela integração com o Cloud SQL Auth Proxy, utilizando Unix socket. A instância terá IP público, mas não permitirá conexões diretas por redes autorizadas e exigirá a utilização de conectores. O acesso administrativo local também utilizará o Cloud SQL Auth Proxy. [Conexão do Cloud Run com o Cloud SQL](https://docs.cloud.google.com/sql/docs/postgres/connect-run)

Serão utilizados usuários PostgreSQL distintos para administração, execução das migrações e acesso pela aplicação. O usuário da aplicação terá apenas as permissões necessárias para manipular os dados, sem privilégios administrativos ou de alteração do schema.

A extensão `pgvector` será habilitada durante a configuração inicial do banco.

#### Cloud Storage

O Cloud Storage guarda os arquivos originais em um bucket privado. Escolhemos o serviço para armazenar os arquivos como objetos e manter no PostgreSQL a chave, os metadados e os trechos indexados. A API usa a chave para localizar o original quando o funcionário abre uma citação, baixa um documento ou o exclui. [Objetos no Cloud Storage](https://docs.cloud.google.com/storage/docs/objects)

O bucket utilizará a classe de armazenamento Standard, namespace plano, controle uniforme de acesso e prevenção de acesso público. O versionamento de objetos e o Soft Delete serão desabilitados, considerando o caráter temporário do ambiente. Os arquivos excluídos não poderão ser recuperados pelo bucket.

No Cloud Run, configure `DOCUMENT_STORAGE_BACKEND=gcs` e informe o nome do bucket em `DOCUMENT_STORAGE_BUCKET`. O SDK usa as credenciais da conta de serviço vinculada ao Cloud Run. Conceda a essa conta o papel `roles/storage.objectUser` exclusivamente no bucket privado. [Identidade do Cloud Run](https://docs.cloud.google.com/run/docs/securing/service-identity#call-google-cloud-apis-with-the-service-identity) · [Permissões do Cloud Storage](https://docs.cloud.google.com/storage/docs/access-control/iam-permissions#object_permissions)

Se o log indicar um commit incerto ou uma falha na limpeza, procure a `storage_key` informada no log na tabela `documents` e no armazenamento do mesmo ambiente. Preserve o arquivo se ainda houver um registro para a chave. Se confirmar que o registro está ausente e o arquivo ainda existe, avalie a remoção manual. O nome original pode se repetir entre documentos.

#### Pub/Sub

Na integração do Gmail, o Pub/Sub entrega à API no Cloud Run os avisos de alteração da caixa de entrada. Ao receber um aviso, a API consulta o Gmail para obter as mensagens e registra cada uma pela entrada comum. A caixa integrada e o ID da mensagem no Gmail são usados para definir o UUID da entrada. A entrega do canal define o recorte da consulta à caixa. [Avisos do Gmail](https://developers.google.com/workspace/gmail/api/guides/push) · [Listagem de mensagens](https://developers.google.com/workspace/gmail/api/guides/list-messages)

#### Cloud Tasks

Cada tarefa leva o UUID de uma entrada persistida e chama a rota de processamento no Cloud Run. Configure a fila da demonstração para disparar uma triagem por vez. Como a mesma tarefa pode ser entregue novamente, a API usa o estado da entrada no PostgreSQL para evitar duplicação de resultados. Quando a aplicação registra uma falha de análise antes de criar a solicitação, o funcionário pode pedir outra tentativa pela tela de Triagem, conforme o RF47. [Cloud Tasks com Cloud Run](https://docs.cloud.google.com/run/docs/triggering/using-tasks) · [Limites de execução da fila](https://docs.cloud.google.com/tasks/docs/configuring-queues) · [Requisitos](requisitos.md)

#### Cloud Scheduler

O Cloud Scheduler chama periodicamente a API para recuperar entradas que foram persistidas e ficaram sem enfileiramento. A API no Cloud Run consulta o banco e solicita o enfileiramento dessas entradas no Cloud Tasks.

Quando o Gmail estiver integrado por Pub/Sub, uma chamada diária do Scheduler aciona a renovação da inscrição de avisos da caixa (`watch`). Essas chamadas chegam ao Cloud Run mesmo quando o serviço está com zero instâncias. [Cloud Scheduler com Cloud Run](https://docs.cloud.google.com/run/docs/triggering/using-scheduler) · [Renovação do watch do Gmail](https://developers.google.com/workspace/gmail/api/guides/push#renew_mailbox_watch)

#### Secret Manager

O Secret Manager armazena as credenciais do banco, a chave de assinatura dos tokens JWT, a eventual chave de API do Gemini e as credenciais das integrações com Gmail e WhatsApp.

A conta de serviço do Cloud Run recebe acesso apenas aos segredos que a API precisa usar. As credenciais administrativas e de migração do PostgreSQL não serão disponibilizadas à aplicação, sendo utilizadas exclusivamente pelos procedimentos administrativos executados localmente.

Os segredos utilizados pelo backend serão disponibilizados como variáveis de ambiente do Cloud Run, referenciando versões específicas do Secret Manager. Os segredos não são incorporados ao código-fonte, às imagens de contêiner ou ao build do frontend.

Escolhemos o serviço para controlar o acesso e a troca de versões das credenciais em um único lugar. [Segredos no Cloud Run](https://docs.cloud.google.com/run/docs/configuring/services/secrets)

## Autenticação da aplicação

A autenticação dos funcionários é realizada pela API FastAPI, que valida as credenciais dos usuários armazenados no PostgreSQL e emite tokens JWT. O frontend envia esses tokens nas requisições às rotas protegidas. O Firebase Hosting é utilizado exclusivamente para hospedar a interface, sem utilizar o Firebase Authentication.

As chamadas internas do Cloud Tasks e do Cloud Scheduler utilizarão contas de serviço dedicadas e tokens OIDC. A API deverá validar os tokens e verificar se a identidade corresponde àquela autorizada para executar a operação.

O acesso aos serviços Google Cloud pelo backend utilizará a identidade da conta de serviço vinculada ao Cloud Run, sem necessidade de arquivos de credenciais ou chaves de contas de serviço. As permissões IAM serão concedidas de acordo com as responsabilidades de cada identidade. [Identidade do Cloud Run](https://docs.cloud.google.com/run/docs/securing/service-identity)

## Configuração dos agentes

A camada de agentes usa Google ADK e tem `gemini-3.8-flash` como modelo padrão no código. O modelo pode ser alterado pela variável `GEMINI_AGENT_MODEL`. Sua disponibilidade será verificada durante o provisionamento. [Camada de agentes](../backend/api/agents/README.md)

Serão consideradas duas modalidades de acesso aos modelos Gemini:

- **Gemini Developer API:** acesso por uma chave de API dedicada à aplicação, armazenada no Secret Manager.
- **Vertex AI:** acesso por meio da identidade da conta de serviço vinculada ao Cloud Run, utilizando Application Default Credentials (ADC).

A modalidade será escolhida durante o provisionamento, considerando a disponibilidade do modelo, as cotas, os custos, os créditos disponíveis e os requisitos de privacidade dos dados. Apenas uma modalidade será configurada por vez.

A utilização de modalidades gratuitas será restrita a dados adequados às suas condições de privacidade. Dados pessoais, sensíveis ou confidenciais não serão enviados à modalidade gratuita da Gemini Developer API.

[Gemini Developer API](https://ai.google.dev/gemini-api/docs) · [Vertex AI](https://cloud.google.com/vertex-ai)

## Provisionamento, publicação e desprovisionamento

O provisionamento dos recursos e a publicação da aplicação serão automatizados por scripts Python utilizando as CLIs do Google Cloud e do Firebase. Os scripts serão versionados no repositório e acompanhados de instruções para reproduzir, atualizar e excluir o ambiente.

O provisionamento deverá permitir execuções repetidas sem duplicar recursos, substituir credenciais existentes ou excluir dados. A configuração dos recursos será parametrizável, permitindo recriar a infraestrutura em outro projeto Google Cloud.

A publicação do backend consiste na construção local da imagem Docker, no envio ao Artifact Registry, na execução das migrações do banco de dados e na implantação de uma nova revisão no Cloud Run. O frontend é compilado separadamente e publicado no Firebase Hosting.

As migrações do Alembic serão executadas localmente por meio do Cloud SQL Auth Proxy, utilizando um usuário PostgreSQL dedicado. As migrações serão aplicadas antes da publicação da nova revisão do backend, e o procedimento será interrompido caso ocorra uma falha. As migrações não serão executadas durante a inicialização dos contêineres.

Escolhemos essa abordagem para reduzir o tempo e a complexidade de implementação, considerando o tamanho do projeto e as necessidades da demonstração. O uso de Terraform e a implementação de pipelines de CI/CD ficam fora do escopo da entrega de infraestrutura.

A infraestrutura será provisionada inicialmente pelo período necessário para validar os scripts e a publicação da aplicação. Não será mantida ativa durante todo o desenvolvimento sem necessidade. O ambiente poderá ser recriado posteriormente para integração, testes finais e demonstração.

Após a utilização, os recursos dedicados à aplicação, incluindo o projeto Google Cloud associado ao Firebase, serão excluídos para evitar custos recorrentes. O desprovisionamento será automatizado e exigirá confirmação explícita do responsável. Antes da exclusão, será avaliada a necessidade de exportar os dados que devam ser preservados.

Os scripts permitirão recriar o ambiente posteriormente, sem depender dos recursos anteriormente provisionados.

## Custos previstos

As estimativas consideram os recursos configurados em Iowa (`us-central1`), o volume reduzido de utilização e o caráter temporário do ambiente. A utilização das franquias gratuitas depende dos limites efetivamente disponíveis, e eventuais créditos promocionais serão verificados antes do provisionamento.

As referências mensais permitem estimar os custos dos serviços em um período maior de utilização, mas não representam a intenção de manter a infraestrutura ativa permanentemente.

#### Google Cloud Run

Para a demonstração, a estimativa usa os preços de Iowa (`us-central1`) com cobrança por requisição e zero instâncias mínimas. O Google cobra CPU e memória pelo tempo faturável da instância, que inclui processar requisições, iniciar e encerrar. [Modalidades de cobrança](https://docs.cloud.google.com/run/docs/configuring/billing-settings) · [Preços do Cloud Run](https://cloud.google.com/run/pricing)

| Componente | Tarifa em Iowa | Franquia mensal |
| --- | --- | --- |
| CPU | US$ 0,000024 por vCPU-segundo | 180.000 vCPU-segundos |
| Memória | US$ 0,0000025 por GiB-segundo | 360.000 GiB-segundos |
| Requisições | US$ 0,40 por milhão | 2 milhões |

Com até 100 triagens por dia durante 30 dias, estimando 30 segundos faturáveis por triagem, 1 vCPU e 512 MiB, as 3.000 triagens consumiriam cerca de 90.000 vCPU-segundos e 45.000 GiB-segundos. O custo desse processamento é de aproximadamente US$ 2,27 por mês antes da franquia e US$ 0 com a franquia disponível. A franquia é compartilhada pela conta de faturamento. As chamadas do chat e dos webhooks também consomem essa franquia. O tráfego de saída pode ter cobrança própria, assim como os demais serviços e as chamadas ao modelo. [Preços e franquia do Cloud Run](https://cloud.google.com/run/pricing)

#### Artifact Registry

A franquia mensal cobre 0,5 GiB-mês de armazenamento por conta de faturamento, e o excedente custa US$ 0,10 por GiB-mês. Considerando até 2 GiB de imagens armazenadas por algumas horas para testes e demonstração, o custo previsto é **US$ 0** com a franquia disponível. Se esse volume permanecer armazenado durante um mês inteiro, o custo estimado será de US$ 0,15. A transferência das imagens para o Cloud Run na mesma região não gera cobrança. [Preços do Artifact Registry](https://cloud.google.com/artifact-registry/pricing)

#### Firebase Hosting

A franquia por projeto cobre 10 GB de armazenamento e 10 GB de transferência por mês. Com 100 MB de arquivos publicados e até 3 GB de transferência no mês, o custo previsto é **US$ 0**. No plano Blaze, o excedente é cobrado a US$ 0,026 por GB de armazenamento e US$ 0,15 por GB transferido. [Franquia e preços do Firebase Hosting](https://firebase.google.com/docs/hosting/usage-quotas-pricing)

#### Cloud SQL

Para a demonstração, uma instância `db-f1-micro` da edição Enterprise em Iowa, em uma única zona, custa cerca de US$ 7,67 por 730 horas. Com 10 GiB de SSD a US$ 0,17 por GiB por mês, a estimativa fica em **US$ 9,37 por mês**, antes de eventuais cobranças adicionais.

Considerando a utilização temporária da infraestrutura, o custo estimado da instância e do armazenamento será:

| Período de utilização | Custo estimado |
| --- | --- |
| 4 horas | US$ 0,05 |
| 24 horas | US$ 0,31 |
| 7 dias | US$ 2,16 |
| 730 horas | US$ 9,37 |

As estimativas pressupõem que a instância e seu armazenamento serão excluídos ao final do período indicado e não incluem eventuais cobranças adicionais de rede, impostos ou créditos promocionais.

O tempo de instância conta enquanto o banco está ligado, mesmo sem consultas. Interromper a execução da instância não elimina necessariamente os custos de armazenamento e IP. [Preços do Cloud SQL](https://cloud.google.com/sql/pricing)

#### Cloud Storage

Em Iowa, o armazenamento Standard custa US$ 0,020 por GiB por mês. Em um bucket com namespace plano, as gravações e listagens (classe A) custam US$ 0,005 por mil operações e as leituras (classe B), US$ 0,0004 por mil. A franquia mensal cobre 5 GB de armazenamento, 5.000 operações de classe A e 50.000 de classe B. Com 1 GiB armazenado durante o mês, 100 operações de classe A e 3.000 operações de classe B, o custo previsto é **US$ 0** com a franquia disponível, antes de eventual cobrança por transferência para fora do Google Cloud. [Preços e franquia do Cloud Storage](https://cloud.google.com/storage/pricing)

#### Pub/Sub

A franquia mensal é de 10 GiB por conta de faturamento e o excedente custa US$ 40 por TiB. As publicações e as entregas contam para o consumo. Com 3.000 notificações pequenas do Gmail e uma entrega por notificação, o custo previsto é **US$ 0** com a franquia disponível. [Preços do Pub/Sub](https://cloud.google.com/pubsub/pricing#throughput_costs)

#### Cloud Tasks

A franquia mensal cobre 1 milhão de operações por conta de faturamento e o excedente custa US$ 0,40 por milhão. Para 3.000 triagens no mês, criar e entregar cada tarefa uma vez consome cerca de 6.000 operações. Cada nova tentativa também conta. O custo previsto é **US$ 0** com a franquia disponível. [Preços do Cloud Tasks](https://cloud.google.com/tasks/pricing)

#### Cloud Scheduler

A franquia cobre três jobs por conta de faturamento e cada job adicional custa US$ 0,10 por 31 dias. A cobrança é por job cadastrado, independentemente do número de execuções. Com um job para recuperar entradas sem enfileiramento e outro para renovar a inscrição do Gmail quando o canal estiver integrado por Pub/Sub, o custo previsto é **US$ 0** com a franquia disponível. [Preços do Cloud Scheduler](https://cloud.google.com/scheduler/pricing)

#### Secret Manager

Com até seis versões ativas de segredos e 10.000 acessos no mês, o custo previsto é **US$ 0** com a franquia disponível. Com replicação automática, uma sétima versão ativa durante todo o mês custaria US$ 0,06. Acima da franquia de acessos, a tarifa é de US$ 0,03 por 10.000 operações. [Preços do Secret Manager](https://cloud.google.com/secret-manager/pricing)

#### Modelos de IA

O custo de inferência dependerá da modalidade de acesso, do modelo utilizado e da quantidade de tokens consumidos pelas chamadas dos agentes.

A modalidade gratuita da Gemini Developer API será priorizada quando estiver disponível e for compatível com os dados utilizados. A utilização de modalidades pagas dependerá da verificação dos preços, créditos disponíveis e eventuais condições de pagamento antecipado, mediante autorização do responsável pela infraestrutura.

[Preços da Gemini Developer API](https://ai.google.dev/gemini-api/docs/pricing) · [Preços do Vertex AI](https://cloud.google.com/vertex-ai/generative-ai/pricing)

#### Controle orçamentário

Será configurado um orçamento mensal de referência equivalente a US$ 1,00, restrito ao projeto Google Cloud da aplicação, com notificações ao atingir 50%, 80% e 100% do valor estabelecido.

O orçamento será parametrizável e os alertas não representam um limite rígido de gastos. Os limites de escalonamento do Cloud Run, o dimensionamento inicial dos recursos e a exclusão do ambiente após sua utilização ajudarão a reduzir o risco de cobranças indesejadas.

Durante o desprovisionamento, será verificado o encerramento dos recursos e a desvinculação do faturamento do projeto. Cobranças referentes ao consumo anterior poderão aparecer após a exclusão. [Orçamentos e alertas do Google Cloud](https://cloud.google.com/billing/docs/how-to/budgets)

## Verificação da demonstração

Antes da demonstração final, a infraestrutura será validada independentemente das integrações ainda em desenvolvimento. Essa validação inclui:

- Reproduzir o provisionamento e a publicação da aplicação utilizando os scripts.
- Acessar o frontend publicado, autenticar-se e utilizar as funcionalidades implementadas.
- Verificar a execução dos agentes no Cloud Run e o acesso ao modelo configurado utilizando dados fictícios.
- Aplicar as migrações em bancos novos e existentes, verificar a disponibilidade do `pgvector` e confirmar a persistência dos dados após uma nova publicação.
- Validar o armazenamento privado dos documentos, as permissões das contas de serviço e a disponibilização segura das credenciais.
- Consultar os logs da aplicação publicada e verificar o procedimento de desprovisionamento.

Na demonstração do sistema completo:

- Envie uma mensagem pelo Gmail e outra pelo WhatsApp com o funcionário desconectado. Confira se cada mensagem gera um cartão e se a fila executa uma triagem por vez. Em cada canal, envie uma resposta nova a uma mensagem anterior e confira que ela gera outro cartão. Repita a entrega do evento da resposta e verifique que o UUID da entrada e os dois cartões daquela conversa são preservados.
- Execute duas vezes o script das 15 mensagens de `pedidos.json`. Confira que cada entrada mantém o UUID e a data original e que a reentrega não gera cartões duplicados.
- Simule uma falha de enfileiramento depois de persistir uma entrada. Confira que a chamada periódica do Scheduler permite à API reenfileirar a entrada e gerar o cartão. Em outro teste, simule falha na análise e valide **Tentar triagem novamente** na tela, conforme o RF47.
- Valide a API de documentos com um bucket privado. Com um JWT válido, envie dois arquivos com o mesmo nome e conteúdos diferentes. Confira os dois registros na lista e compare os bytes de cada download com os originais. Exclua um dos registros e confira se apenas o objeto correspondente foi removido do bucket e se o outro continua disponível.
- Quando a consulta documental e as citações estiverem disponíveis, adicione um documento, consulte seu conteúdo pelo chat e abra o original pela citação.