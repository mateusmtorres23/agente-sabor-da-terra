# Integrações de mensagens

O e-mail é o canal fixo. Para a demonstração, valide primeiro o recebimento pelo WhatsApp com o número de teste da Meta. Use o Telegram como alternativa se a equipe não conseguir validar o recebimento pelo WhatsApp antes da apresentação. Os funcionários escrevem e enviam respostas e notificações pelos canais externos à aplicação.

## Fluxo comum

1. Os adaptadores dos canais, o formulário web e o script de apresentação usam o formato comum de entrada. A entrada guarda o UUID, o texto original, o remetente, o canal de origem, a data de recebimento e o estado da triagem.
2. Persista a entrada antes de iniciar a triagem e antes de confirmar o recebimento ao webhook. Reentregas com o mesmo UUID reaproveitam o registro e preservam a data original. A aplicação usa essa data para acionar o assistente, inclusive em novas tentativas. Se a triagem falhar antes de criar a solicitação, o funcionário pode tentar novamente a partir da entrada registrada.
3. Cada mensagem nova, inclusive uma resposta, passa por triagem própria e gera uma solicitação quando a análise conclui. Reentregas de uma entrada concluída mantêm o cartão já criado.

O RF11 define o recebimento e a criação de uma solicitação por mensagem nova. O RF47 descreve como o funcionário tenta novamente pela tela de Triagem. O RNF03 trata da deduplicação, o RNF05 exige a validação de autenticidade dos webhooks, o RNF07 define a entrada comum e o RNF11 trata da recuperação de falhas. [Requisitos](requisitos.md)

## Identidade da mensagem recebida

O UUID é a chave primária da entrada. Quando a origem fornece um identificador estável, a aplicação usa a origem, seu contexto e esse identificador para obter o mesmo UUID em reentregas. Mensagens com identificadores diferentes geram entradas distintas, mesmo quando o texto coincide. Uma mensagem sem identificador estável recebe um UUID novo.

| Origem | Contexto | Identificador usado para definir o UUID |
| --- | --- | --- |
| Gmail | Caixa de e-mail integrada | ID da mensagem no Gmail |
| WhatsApp | Número integrado que recebeu a mensagem | ID da mensagem no WhatsApp |
| Formulário web | Formulário da aplicação | UUID criado antes do primeiro envio e reutilizado em novas tentativas |
| Script Facepe | Base Facepe | ID do registro em `pedidos.json` |
| Telegram, se integrado | Bot e chat de origem | `message_id` |

Para mensagens dos canais integrados, preserve a data de recebimento fornecida pelo canal quando disponível. Caso contrário, registre o momento em que a aplicação recebeu a mensagem pela primeira vez. O script Facepe usa o campo `data_recebimento` do registro e mantém o canal original para exibição.

## E-mail

Use uma caixa dedicada para receber solicitações. No Gmail, autorize a conta por OAuth 2.0 e use `gmail.readonly` para consultar as mensagens. Uma tarefa agendada pode buscar mensagens novas. Use o `id` da mensagem no Gmail e a caixa de origem para definir o UUID da entrada. Em um aplicativo OAuth externo em modo de teste, o refresh token com escopos do Gmail expira em sete dias. [Autorização](https://developers.google.com/workspace/gmail/api/auth/web-server) · [Escopos](https://developers.google.com/workspace/gmail/api/auth/scopes) · [Consulta de mensagens](https://developers.google.com/workspace/gmail/api/guides/list-messages) · [Expiração do token](https://developers.google.com/identity/protocols/oauth2#expiration)

O Gmail também oferece avisos de alterações na caixa via Pub/Sub. Essa opção requer renovar `watch` e consultar as mensagens da caixa ao receber um aviso. Quando o provedor oferecer IMAP, o adaptador pode usá-lo para leitura com a autenticação aceita pelo serviço. O Gmail aceita OAuth 2.0 para IMAP. [Avisos de alterações do Gmail](https://developers.google.com/workspace/gmail/api/guides/push) · [OAuth para IMAP](https://developers.google.com/workspace/gmail/imap/xoauth2-protocol)

## WhatsApp

Configure o aplicativo na Meta, obtenha o token de acesso da Cloud API e cadastre os contatos da equipe para usar o número de teste fornecido pela Meta. Inscreva o aplicativo na conta do WhatsApp Business para receber eventos de `messages` em uma URL HTTPS pública. [Ambiente de teste da Meta](https://whatsappbusiness.com/developers/developer-hub/) · [Coleção oficial da Cloud API](https://www.postman.com/meta/whatsapp-business-platform/collection/wlk6lh4/whatsapp-cloud-api) · [Guia de webhook da Meta](https://whatsappbusiness.com/blog/how-to-use-webhooks-from-whatsapp-business-api/)

No `GET` de verificação, confira `hub.verify_token` e devolva `hub.challenge` quando o token corresponder ao configurado. Em cada `POST`, valide `X-Hub-Signature-256` com o HMAC-SHA256 do corpo bruto calculado com o segredo do aplicativo. Encaminhe as mensagens de texto recebidas para a triagem. [Exemplo de webhook da Meta](https://github.com/fbsamples/business-messaging-sample-tech-provider-app/blob/main/app/api/webhooks/route.ts) · [Eventos do WhatsApp](https://whatsappbusiness.com/blog/how-to-use-webhooks-from-whatsapp-business-api/)

## Telegram

Crie o bot com `/newbot` no BotFather e guarde o token no backend. Em `setWebhook`, informe uma URL HTTPS e configure `secret_token`. Confira o segredo no cabeçalho `X-Telegram-Bot-Api-Secret-Token` a cada chamada.

No ambiente publicado, utilize webhooks para receber as mensagens sem depender de um processo continuamente ativo. O long polling com `getUpdates` é uma alternativa para ambientes que disponham de um processo contínuo. Use um modo de recebimento por bot. [BotFather](https://core.telegram.org/bots/features#creating-a-new-bot) · [Webhook](https://core.telegram.org/bots/api#setwebhook) · [Long polling](https://core.telegram.org/bots/api#getupdates)

O adaptador do Telegram usa o bot e `message.chat.id` como contexto e `message.message_id` como identificador da mensagem.

Em chat privado, o primeiro contato parte do usuário. Na demonstração, o participante abre o bot, toca em **Iniciar** e escreve uma mensagem de teste para a triagem. [Primeiro contato](https://core.telegram.org/bots#how-are-bots-different-from-users)

## Validação do recebimento

- Em cada canal integrado, envie uma mensagem de teste à aplicação e confira o registro da entrada, a data de recebimento e a análise na triagem. Repita a entrega do mesmo evento e verifique que a aplicação mantém o mesmo UUID e um único cartão.
- Execute o script Facepe duas vezes. Confira que cada registro mantém o mesmo UUID e preserva o `data_recebimento` de `pedidos.json`. Uma expressão como “amanhã” deve usar essa data mesmo se o script rodar em outro dia.
- Nos canais com webhook, verifique que um evento que falha na validação de autenticidade é rejeitado antes de entrar na triagem.

## Execução em nuvem

O backend será publicado no Cloud Run e utilizará a URL HTTPS pública do serviço para receber os webhooks dos canais integrados. As rotas de recebimento aceitarão chamadas externas e validarão a autenticidade dos eventos conforme o mecanismo de cada provedor. As rotas destinadas aos funcionários exigirão autenticação por JWT.

O Cloud Run utilizará cobrança por requisição e zero instâncias mínimas. Webhooks e chamadas agendadas poderão iniciar o serviço mesmo quando não houver instâncias ativas. As integrações deverão utilizar webhooks ou consultas agendadas, sem depender de processos contínuos de polling. [HTTPS](https://docs.cloud.google.com/run/docs/triggering/https-request) · [Escalonamento](https://docs.cloud.google.com/run/docs/about-instance-autoscaling)

As chamadas do Cloud Tasks e do Cloud Scheduler utilizarão contas de serviço dedicadas e tokens OIDC. A API deverá validar esses tokens e verificar se a identidade autenticada está autorizada a executar a operação solicitada. [Cloud Tasks com Cloud Run](https://docs.cloud.google.com/run/docs/triggering/using-tasks) · [Cloud Scheduler com Cloud Run](https://docs.cloud.google.com/run/docs/triggering/using-scheduler)

Configure o Cloud Scheduler para chamar periodicamente a API no Cloud Run e recuperar entradas que foram persistidas e ficaram sem enfileiramento, inclusive com a aplicação ociosa. Após um reinício, a API usa os registros persistidos para retomar o enfileiramento no Cloud Tasks.

Guarde tokens e credenciais das integrações no Secret Manager. Persista os registros de entrada com seus UUIDs e estados de triagem no PostgreSQL hospedado no Cloud SQL. No Cloud Run, os arquivos escritos no contêiner são descartados quando a instância para. [Segredos](https://docs.cloud.google.com/run/docs/configuring/services/secrets) · [Armazenamento do contêiner](https://docs.cloud.google.com/run/docs/container-contract#file_system_access)

Consulte [Infraestrutura](infra.md) para conhecer a configuração dos serviços e os procedimentos previstos de provisionamento, publicação e desprovisionamento.