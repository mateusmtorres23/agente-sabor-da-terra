# Integrações de mensagens

O e-mail é o canal fixo. Para a demonstração, valide primeiro o WhatsApp com o número de teste da Meta. Use o Telegram como alternativa se a equipe não conseguir validar o fluxo do WhatsApp antes da apresentação.

## Fluxo comum

1. Cada adaptador entrega à aplicação o canal, a conta receptora, o identificador externo da mensagem normalizado para ser único nessa conta, o remetente, o texto original e a data de recebimento no canal. Preserve essa data nas reentregas e mantenha as referências de conversa e de resposta fornecidas pelo canal. Um formulário web poderá usar a mesma entrada.
2. Registre a mensagem com uma chave única por canal, conta e identificador externo. Responda ao webhook depois de persistir o evento. Ao processar a triagem, a aplicação usa o registro para acionar o assistente. Reentregas ou consultas repetidas reaproveitam o registro existente.
3. Vincule a mensagem a uma solicitação aberta quando houver uma referência confiável no histórico, o contato corresponder ao vínculo e a mensagem der continuidade à mesma demanda. Abra nova triagem para um pedido independente, mesmo que chegue como resposta direta na conversa anterior. Abra nova triagem também quando o vínculo estiver ausente, for ambíguo ou apontar para uma solicitação encerrada.
4. A pedido do funcionário, o assistente prepara o rascunho da resposta ou da notificação. O funcionário pode editar o texto e confere o destinatário e o canal antes de autorizar o envio. As respostas ao remetente seguem pelo canal de origem.
5. Antes do envio, registre o texto autorizado, o destino, o canal e quem confirmou. Aplique a RN22 antes de acionar o provedor. Use o RNF03 e o RNF08 para tratar confirmações repetidas ou simultâneas. Registre o retorno do provedor e atualize o histórico se o canal informar um resultado posterior. Registre a aceitação pelo canal e a confirmação de entrega como informações distintas, quando disponíveis. As novas tentativas seguem a RN18.

As regras de compromisso, vínculo, envio, reenvio e compartilhamento estão na RN11, nas RN16 a RN18, na RN21 e na RN22 dos [requisitos](requisitos.md).

## E-mail

Use uma caixa dedicada para receber solicitações e enviar respostas. Com Gmail, autorize a conta por OAuth 2.0 e use `gmail.readonly` para consultar mensagens e `gmail.send` para enviar o texto aprovado. Uma tarefa agendada pode buscar mensagens novas e registrar o `id` de cada uma. Para responder na mesma conversa, use o `threadId`, os cabeçalhos `In-Reply-To` e `References` e o assunto da conversa. Em um aplicativo OAuth externo em modo de teste, o refresh token com escopos do Gmail expira em sete dias. [Autorização](https://developers.google.com/workspace/gmail/api/auth/web-server) · [Escopos](https://developers.google.com/workspace/gmail/api/auth/scopes) · [Consulta de mensagens](https://developers.google.com/workspace/gmail/api/guides/list-messages) · [Conversas](https://developers.google.com/workspace/gmail/api/guides/threads) · [Expiração do token](https://developers.google.com/identity/protocols/oauth2#expiration)

O Gmail também oferece notificações via Pub/Sub. Essa opção requer renovar `watch` e consultar o histórico da caixa para buscar as alterações. Quando o provedor oferecer IMAP e SMTP, o adaptador pode usar IMAP para leitura e SMTP para envio com a autenticação aceita pelo serviço. No Gmail, os dois protocolos aceitam OAuth 2.0. [Notificações do Gmail](https://developers.google.com/workspace/gmail/api/guides/push) · [IMAP e SMTP](https://developers.google.com/workspace/gmail/imap/imap-smtp) · [OAuth para IMAP e SMTP](https://developers.google.com/workspace/gmail/imap/xoauth2-protocol)

## WhatsApp

Configure o aplicativo na Meta, obtenha o token de acesso da Cloud API e cadastre os contatos da equipe para usar o número de teste fornecido pela Meta. Inscreva o aplicativo na conta do WhatsApp Business para receber eventos de `messages` em uma URL HTTPS pública. [Ambiente de teste da Meta](https://whatsappbusiness.com/developers/developer-hub/) · [Coleção oficial da Cloud API](https://www.postman.com/meta/whatsapp-business-platform/collection/wlk6lh4/whatsapp-cloud-api) · [Guia de webhook da Meta](https://whatsappbusiness.com/blog/how-to-use-webhooks-from-whatsapp-business-api/)

No `GET` de verificação, confira `hub.verify_token` e devolva `hub.challenge` quando o token corresponder ao configurado. Em cada `POST`, valide `X-Hub-Signature-256` com o HMAC-SHA256 do corpo bruto calculado com o segredo do aplicativo. As mensagens de texto seguem para a triagem e os eventos de status atualizam o histórico de envios. [Exemplo de webhook da Meta](https://github.com/fbsamples/business-messaging-sample-tech-provider-app/blob/main/app/api/webhooks/route.ts) · [Eventos do WhatsApp](https://whatsappbusiness.com/blog/how-to-use-webhooks-from-whatsapp-business-api/)

Teste com uma mensagem enviada pelo WhatsApp de um contato cadastrado. Confira se ela aparece na triagem e se o mesmo contato recebe a resposta após a confirmação do funcionário. Valide também o recebimento da notificação pelo contato que representa o produtor. Para testar a notificação em texto livre, o produtor de teste pode enviar uma mensagem ao número de teste e abrir a janela de atendimento antes do envio.

Confirme o consentimento dos contatos para receber mensagens pelo WhatsApp. A janela de atendimento permite respostas em texto livre por 24 horas a partir da última mensagem de cada contato. Para iniciar uma conversa ou enviar fora da janela, use um modelo aprovado pela Meta. O funcionário revisa os valores dos campos do modelo antes de confirmar. [Política de Mensagens do WhatsApp Business](https://whatsappbusiness.com/pt-br/policy/)

## Telegram

Crie o bot com `/newbot` no BotFather e guarde o token no backend. Em `setWebhook`, informe uma URL HTTPS e configure `secret_token`. Confira o segredo no cabeçalho `X-Telegram-Bot-Api-Secret-Token` a cada chamada. Quando houver um processo contínuo, o adaptador pode usar long polling com `getUpdates`. Use um modo de recebimento por bot. [BotFather](https://core.telegram.org/bots/features#creating-a-new-bot) · [Webhook](https://core.telegram.org/bots/api#setwebhook) · [Long polling](https://core.telegram.org/bots/api#getupdates)

O adaptador do Telegram combina `message.chat.id` e `message.message_id` para formar o identificador externo da mensagem. O adaptador usa o mesmo escopo ao referenciar a mensagem respondida.

Em chat privado, o primeiro contato parte do usuário. Na demonstração, o participante que representa o produtor abre o bot e toca em **Iniciar**. Associe o `chat_id` recebido ao cadastro desse produtor e use-o em `sendMessage` após a confirmação do funcionário. Para responder ao remetente de uma solicitação, use o `chat_id` da mensagem de origem. [Primeiro contato](https://core.telegram.org/bots#how-are-bots-different-from-users) · [Envio de mensagens](https://core.telegram.org/bots/api#sendmessage)

## Execução em nuvem

Se o backend rodar no Cloud Run, a URL HTTPS do serviço pode receber os webhooks. A rota de recebimento precisa aceitar chamadas externas e validar a credencial do provedor. As rotas internas exigem a autenticação dos funcionários. Webhooks e chamadas agendadas podem iniciar o serviço a partir de zero instâncias. Para manter polling contínuo em um serviço Cloud Run, configure pelo menos uma instância mínima e CPU disponível fora das requisições. Para consultar e-mail por agendamento, o Cloud Scheduler pode acionar um serviço privado via OIDC com uma conta autorizada a invocá-lo. [HTTPS](https://docs.cloud.google.com/run/docs/triggering/https-request) · [Escalonamento](https://docs.cloud.google.com/run/docs/about-instance-autoscaling) · [Alocação de CPU](https://docs.cloud.google.com/run/docs/configuring/billing-settings) · [Agendamento](https://docs.cloud.google.com/run/docs/triggering/using-scheduler)

Configure um acionamento que processe os eventos pendentes e gere as ocorrências agendadas mesmo com a aplicação ociosa. Após reinício, retome o trabalho a partir dos registros persistidos. No Cloud Run, o Cloud Scheduler pode chamar essa rotina periodicamente.

Guarde tokens e credenciais no gerenciador de segredos do ambiente. Persista mensagens, vínculos, chaves de deduplicação e estados de envio em armazenamento durável. No Cloud Run, os arquivos escritos no contêiner são descartados quando a instância para. [Segredos](https://docs.cloud.google.com/run/docs/configuring/services/secrets) · [Armazenamento do contêiner](https://docs.cloud.google.com/run/docs/container-contract#file_system_access)
