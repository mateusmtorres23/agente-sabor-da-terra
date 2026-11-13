# User stories

O usuário é o funcionário da cooperativa. As referências RF, RN e RNF apontam para [Requisitos](requisitos.md).

## US01 - Acessar a plataforma

Como funcionário, quero me autenticar para consultar informações e trabalhar nas solicitações da cooperativa.

Requisitos: RF16, RNF05.

Critérios de aceitação:

- Credenciais válidas permitem acessar as funções internas.
- Sem autenticação, consultas e alterações internas são rejeitadas.

## US02 - Revisar uma solicitação

Como funcionário, quero receber uma análise da mensagem para entender a demanda e suas pendências antes de decidir.

Requisitos: RF02, RF03, RF04, RF11, RF12, RF15, RF26 a RF29; RN06 a RN08, RN16; RNF03, RNF06.

Critérios de aceitação:

- As 15 mensagens importadas aparecem na caixa de entrada da triagem com a indicação de que são da amostra. Repetir a carga mantém um único registro por mensagem.
- As mensagens novas dos canais integrados entram na mesma caixa de entrada e passam pela mesma triagem que as mensagens da amostra.
- O sistema preserva o texto original, o remetente, o canal e a data de recebimento de cada mensagem, além do identificador de origem quando disponível. Uma nova entrega da mesma mensagem pelo canal integrado mantém um único registro.
- O sistema, ao receber um novo pedido como resposta direta a uma mensagem de outra solicitação aberta do mesmo contato, cria uma solicitação separada e preserva a anterior.
- O sistema registra na solicitação aberta a resposta que dá continuidade à demanda e tem vínculo inequívoco. Atualiza a análise, as pendências e o estado dessa solicitação conforme o RF15. O sistema abre nova triagem quando o vínculo é incerto ou a solicitação anterior está encerrada.
- O sistema, se o Telegram estiver integrado, registra separadamente duas mensagens com o mesmo `message_id` em chats diferentes do mesmo bot. O sistema, ao receber uma reentrega de uma delas, reaproveita apenas o registro do chat correspondente.
- O cartão apresenta o resumo, o tipo, a urgência justificada e as pendências.
- O funcionário pode abrir o chat pelo cartão para consultar a análise inicial assim que estiver disponível e ver o histórico ao voltar à conversa. Se a solicitação tiver mensagens recebidas, o funcionário pode consultar o texto original pelo chat.
- A análise organiza os dados extraídos e preserva condições como "se tiver", a frequência de fornecimento e intenções adicionais, como uma oferta acompanhada de solicitação de cadastro.
- O assistente interpreta a mensagem PED-2026-011 em inglês e apresenta a triagem em português.
- Ao consultar o PED-2026-003 em novembro, o cartão mantém 29/10 como data de entrega solicitada e indica que o prazo venceu.

## US03 - Esclarecer ambiguidades

Como funcionário, quero discutir os pontos incertos com o assistente para completar a análise sem adivinhar a intenção do remetente.

Requisitos: RF01, RF07, RF10, RF13; RN03, RN06.

Critérios de aceitação:

- Produto indefinido, quantidade agregada ou data conflitante gera uma pergunta específica, preservando as informações já compreendidas.
- Quando o remetente usa uma expressão como "amanhã", o assistente calcula a data a partir do recebimento daquela mensagem. Retomar a conversa em outro dia não altera a interpretação.
- O assistente registra o esclarecimento na conversa e atualiza a análise, a sugestão e os alertas afetados, preservando a mensagem original.
- Perguntas de acompanhamento usam o contexto daquela conversa, sem incorporar dados de outra solicitação.

## US04 - Avaliar uma sugestão de atendimento

Como funcionário, quero conhecer os produtores candidatos para comparar alternativas de atendimento.

Requisitos: RF06, RF14, RF23, RF30 a RF32; RN01 a RN04, RN10, RN13, RN23.

Critérios de aceitação:

- A sugestão identifica os produtores candidatos e cita as fontes usadas.
- Quando houver dados suficientes, a sugestão mostra a capacidade estimada de cada candidato para o produto, com unidade, período e fonte. O assistente indica o que o funcionário ainda precisa confirmar sobre a disponibilidade.
- Para um pedido cadastrado, a sugestão considera a quantidade de cada item que ainda falta alocar.
- O assistente exclui produtores inaptos da sugestão e indica o motivo. O assistente apresenta dados ausentes ou conflitantes como pendências e indica a aptidão sem comprovação como pendente, separada dos candidatos aptos.
- Na triagem do PED-2026-004, se a base só informar o número do DAP ou CAF, o assistente aponta que falta comprovar a vigência e cita o contrato do PNAE.
- O funcionário pode discutir alternativas no chat e registra as alocações escolhidas na gestão do pedido.

## US05 - Acompanhar a triagem

Como funcionário, quero consultar a situação das solicitações para identificar o que ainda depende de decisão.

Requisitos: RF12, RF15; RN10.

Critérios de aceitação:

- Na fila de triagem, o funcionário vê o estado atual de cada solicitação e as pendências existentes.
- Uma solicitação nova aparece como recebida. Quando a análise começa, o sistema muda o estado para em análise. Se faltar informação para decidir, muda para aguardando informações. Quando já dá para decidir, inclusive se o atendimento for inviável, muda para pronta para decisão. Se um esclarecimento resolver a última pendência que impedia a decisão, a solicitação passa para pronta para decisão.
- Sem fornecedor apto, a análise explica o motivo. O funcionário pode buscar esclarecimentos ou encerrar sem atendimento.
- Quando o funcionário encerra a solicitação, o sistema muda o estado para encerrada e registra o resultado da triagem e as pendências restantes.

## US06 - Consultar documentos e dados

Como funcionário, quero fazer perguntas sobre os registros da cooperativa para responder às demandas com fontes verificáveis.

Requisitos: RF01, RF05, RF06, RF07, RF17; RN01, RN03, RN05, RN06; RNF06.

Critérios de aceitação:

- A consulta pode combinar documentos e dados operacionais na mesma conversa.
- Em uma consulta iniciada no chat sem data informada, o assistente usa a data da consulta e a indica na resposta.
- A resposta identifica documentos e registros ou trechos que sustentam as afirmações. Consultas sobre certificação verificam validade e produto coberto; consultas sobre lote identificam sua origem registrada.
- A consulta ao LOT-2026-0094 informa 300 unidades de alface. No LOT-2026-0099, o assistente indica que "40 maços (kg)" tem unidade ambígua e deixa a quantidade fora dos totais.
- Preços informam vigência e condições. Informação ausente ou conflitante é explicitada, sem completar a resposta por suposição.
- A citação permite ler o documento completo na plataforma e baixar o arquivo original usado na resposta, mesmo após a substituição no cadastro.

## US07 - Consultar e baixar o resumo de um produtor

Como funcionário, quero gerar e baixar em PDF um resumo por produtor para informar suas vendas, pedidos alocados e pendências financeiras.

Requisitos: RF08, RF18, RF23; RN03, RN09, RN14; RNF04.

Critérios de aceitação:

- O resumo identifica produtor, período e data de referência, com fontes dos valores e registros apresentados.
- O resumo usa a data da transação para selecionar vendas e a data de pagamento para selecionar pagamentos registrados. No PED-2026-012, os R$ 940 de vendas ao Mercado Bom Preço entram em setembro e o pagamento registrado entra em outubro. Quantidades respeitam produto e unidade.
- O resumo distingue pendências vencidas e a vencer na data de referência, inclusive as de períodos anteriores. Quando não encontra registros, o assistente informa a ausência. O pagamento registrado, por si só, não comprova repasse bancário.
- No resumo da produtora P001 com referência em 30/09/2026, os R$ 940 do Mercado Bom Preço aparecem como valor a vencer. O vencimento é em 02/10/2026 e o pagamento consta em 01/10/2026.
- O resumo lista as alocações do produtor com entrega prevista no período, inclusive quando só parte do intervalo de entrega cai no período. Após o cancelamento do pedido, as alocações removidas deixam de aparecer nos novos resumos.
- O resumo é acompanhado da opção "Baixar resumo em PDF". O arquivo preserva o conteúdo e as fontes exibidos.

## US08 - Preparar e enviar uma notificação

Como funcionário, quero preparar e enviar uma notificação para comunicar uma demanda ao produtor.

Requisitos: RF09, RF40 a RF42; RN11, RN14, RN17, RN21, RN22.

Critérios de aceitação:

- O rascunho identifica o produtor, os produtos, as quantidades e os prazos conhecidos e indica o que ainda precisa de confirmação.
- O sistema permite enviar uma consulta de disponibilidade sem alocação confirmada se as condições da RN17 forem atendidas. O sistema aplica as verificações da RN22 quando o texto revisado confirma um compromisso de fornecimento.
- A notificação só comunica uma alocação futura como confirmada se os dados atuais comprovarem a aptidão do produtor. Se faltar comprovação obrigatória, a aplicação sinaliza a pendência para revisão.
- O funcionário pode editar e copiar o texto e escolher um canal integrado.
- O sistema mostra o destinatário e o canal da notificação para o funcionário conferir antes de confirmar.
- Na demonstração, o envio fica disponível apenas para destinos de teste que a equipe vinculou ao produtor. Se faltar destino válido ou o canal impedir o envio, a aplicação informa o motivo e oferece a cópia do rascunho conforme a RN21.
- O sistema só envia a versão revisada após a confirmação explícita do funcionário.
- O assistente deixa dados pessoais ou bancários das fontes fora do texto da notificação e da versão copiável até o funcionário autorizar os dados específicos para aquele destinatário.
- O sistema registra no histórico o texto autorizado, o funcionário que confirmou, o destinatário, o canal e o resultado do envio.
- O sistema bloqueia o envio da notificação de compromisso e informa o motivo se o pedido for cancelado antes da confirmação ou entre a confirmação e o disparo.
- Se, após uma falha, as alocações deixarem de cobrir a quantidade prometida, o sistema bloqueia o reenvio do rascunho e informa o motivo.

## US09 - Retomar o trabalho

Como funcionário, quero reencontrar as solicitações e suas conversas para continuar a triagem após sair da aplicação.

Requisitos: RF10; RNF01.

Critérios de aceitação:

- Após reabrir a aplicação e se autenticar, o funcionário encontra mensagens, histórico de envios, análises, conversas, cadastros, pedidos, agendamentos e alocações.
- Ao retomar uma conversa, o assistente considera seus esclarecimentos anteriores e mantém o contexto separado das demais solicitações.

## US10 - Recuperar uma operação com falha

Como funcionário, quero saber quando uma operação falhou e poder tentar novamente para continuar o atendimento.

Requisitos: RN18; RNF02, RNF03, RNF08 a RNF10.

Critérios de aceitação:

- A interface indica processamento e informa falhas. Após 60 segundos sem conclusão, informa a demora. Para envios, só oferece nova tentativa após falha confirmada, conforme a RN18. Nas demais operações, oferece nova tentativa após o aviso de demora.
- A solicitação permanece disponível. Repetir a mesma operação mantém um único registro, inclusive na confirmação de pedidos e agendamentos pelo chat, na geração de ocorrências e no cadastro de alocações. Uma alteração rejeitada mantém o registro anterior.
- O resultado atrasado de uma tentativa anterior não substitui análises ou esclarecimentos mais recentes.
- O sistema aciona no máximo uma tentativa ao receber a mesma confirmação mais de uma vez ou duas confirmações simultâneas da mesma versão do rascunho para o mesmo destinatário e canal. O sistema, após um envio bem-sucedido, bloqueia nova tentativa dessa versão para o mesmo destinatário e canal.
- O sistema mantém o reenvio bloqueado durante a tentativa. Se a tentativa terminar sem confirmação do resultado, o histórico mostra "Resultado incerto" e explica que reenviar pode duplicar a mensagem. O reenvio fica bloqueado mesmo se o funcionário editar o rascunho. Se o canal confirmar o resultado mais tarde, o sistema atualiza o histórico.
- O sistema libera uma nova tentativa após confirmar a falha anterior e receber nova confirmação explícita do funcionário.

## US11 - Manter os cadastros

Como funcionário, quero manter os cadastros de produtores, produtos e documentos para trabalhar com dados atualizados.

Requisitos: RF19, RF33, RF34; RN19; RNF06.

Critérios de aceitação:

- O funcionário pode criar, consultar e editar produtores, produtos e documentos. Pode excluir registros sem vínculos.
- O sistema bloqueia a exclusão de registros vinculados a pedidos, alocações, agendamentos, lotes, transações financeiras ou citações.
- Ao bloquear a exclusão, o sistema informa ao funcionário qual vínculo impede a operação.
- As consultas e sugestões do assistente usam os cadastros atualizados após essas operações.
- Após editar um produtor da base e excluir um documento importado sem vínculos, uma nova carga na mesma base preserva a edição e a exclusão.

## US12 - Gerenciar pedidos

Como funcionário, quero gerenciar os pedidos da cooperativa para acompanhar as demandas cadastradas.

Requisitos: RF20, RF35; RN14.

Critérios de aceitação:

- O funcionário pode criar, consultar, editar e cancelar pedidos.
- No cadastro manual e na edição, o funcionário pode informar uma data ou um intervalo de entrega. O pedido salvo mostra o prazo informado.
- No cadastro manual e na edição, o funcionário pode registrar condições para todo o pedido e para itens específicos. Ao consultar o pedido salvo, ele vê a que parte do pedido cada condição se aplica.
- A aplicação registra o cancelamento e exclui as alocações do pedido na mesma operação. O pedido continua consultável com o estado cancelado.

## US13 - Cadastrar um pedido pelo chat

Como funcionário, quero revisar e confirmar um pedido no chat para registrá-lo na gestão de pedidos.

Requisitos: RF20, RF21, RF35, RF37, RF38; RN16, RN20; RNF03.

Critérios de aceitação:

- O assistente apresenta no chat um rascunho com o comprador, os itens, as quantidades, as unidades, o prazo e as condições de atendimento.
- Se o comprador pedir entrega de 4 a 8 de novembro, o rascunho mostra o intervalo e o sistema o salva ao confirmar o pedido. Se o funcionário escolher um dia específico na revisão, o sistema salva a data escolhida.
- Ao revisar o rascunho no chat, o funcionário pode ajustar os dados e decidir se inclui os itens solicitados sob condição.
- Se uma resposta do comprador vinculada à solicitação corrigir a quantidade de 30 para 15 enquanto o rascunho estiver aberto, o funcionário vê a correção antes de confirmar a versão que deseja cadastrar.
- Após a confirmação explícita do funcionário, o sistema cadastra a versão revisada. O pedido fica disponível para consulta e edição na gestão de pedidos.
- Quando o pedido é cadastrado pela triagem, o funcionário pode abri-lo pelo chat da solicitação de origem, inclusive depois de reabrir a conversa.
- Ao consultar o pedido cadastrado a partir do PED-2026-004, o funcionário encontra a exigência de certificação orgânica no item de mel.

## US14 - Agendar pedidos

Como funcionário, quero agendar pedidos para que cada ocorrência entre na triagem com a antecedência definida.

Requisitos: RF22, RF25, RF37 a RF39; RN15, RN27; RNF03.

Critérios de aceitação:

- O funcionário pode cadastrar, consultar, editar e cancelar agendamentos semanais.
- O sistema registra o comprador, os itens, as quantidades, as unidades, as condições de atendimento confirmadas, a primeira data de fornecimento e a antecedência da triagem em dias corridos ao salvar um agendamento.
- O assistente prepara o rascunho do agendamento no chat. O funcionário pode revisar e ajustar os dados antes de confirmar.
- O sistema cadastra a versão revisada do agendamento após a confirmação explícita do funcionário no chat.
- Na data programada para a triagem, cada ocorrência gera uma única solicitação vinculada ao agendamento. A solicitação traz o comprador, os itens, as quantidades, as unidades, as condições e a data de fornecimento. Um fornecimento de terça-feira com dois dias de antecedência entra na triagem no domingo.
- O sistema, ao retomar o serviço ou salvar um agendamento novo ou editado, gera de imediato as solicitações das ocorrências pendentes com triagem prevista para hoje ou antes e fornecimento para hoje ou depois. O sistema registra como perdida a ocorrência cuja data de fornecimento já passou.
- Um agendamento salvo na segunda-feira para fornecimento na terça-feira, com dois dias de antecedência, gera a primeira solicitação na segunda-feira, uma única vez.
- O sistema, ao salvar um agendamento de fornecimento para hoje com antecedência zero depois da rotina do dia, gera a primeira solicitação de imediato, uma única vez. O sistema faz o mesmo ao retomar o serviço quando essa ocorrência ainda estiver pendente.
- Alterar ou cancelar um agendamento afeta apenas ocorrências pendentes.
- Se a entrega de terça-feira já entrou na triagem e o funcionário muda o dia da série para quinta-feira da mesma semana, a solicitação de terça mantém os dados originais. A primeira entrega de quinta-feira fica para a semana seguinte, mesmo que a solicitação de terça tenha sido gerada no domingo anterior.

## US15 - Gerenciar alocações

Como funcionário, quero gerenciar as alocações de cada item do pedido para registrar quem atenderá a demanda.

Requisitos: RF20, RF23; RN03, RN12 a RN14, RN24 a RN26.

Critérios de aceitação:

- O funcionário pode cadastrar, consultar, editar e excluir alocações. Cada alocação identifica o item do pedido, o produtor, a quantidade e a unidade.
- O sistema exige pedido ativo e disponibilidade confirmada pelo funcionário para cadastrar ou editar uma alocação.
- A quantidade alocada é positiva. O sistema converte as quantidades para a unidade do item antes de verificar se a soma respeita o limite solicitado. Se a unidade for incompatível ou o total ultrapassar o limite, o sistema rejeita o salvamento.
- Se o funcionário tentar cadastrar ou editar uma alocação para o produtor P015, marcado como inativo na base, o sistema impede o salvamento e informa o motivo.
- O funcionário precisa ajustar ou excluir as alocações afetadas antes de salvar uma alteração do pedido que entre em conflito com elas.
- O sistema rejeita o salvamento de uma alocação após o cancelamento do pedido, mesmo se o formulário tiver sido aberto antes. O sistema mantém o pedido cancelado sem alocações mesmo se o salvamento e o cancelamento forem simultâneos.

## US16 - Responder ao remetente

Como funcionário, quero revisar uma resposta para esclarecer a solicitação ou informar o resultado da triagem ao remetente.

Requisitos: RF24, RF40 a RF43; RN11, RN17, RN21, RN22.

Critérios de aceitação:

- O assistente, a pedido do funcionário, prepara um rascunho de resposta. O funcionário pode editar e copiar o texto, inclusive nas mensagens da amostra.
- O assistente, quando o remetente pede documentos, dados pessoais ou dados bancários, avisa o funcionário. O assistente lista, no aviso do PED-2026-009, os documentos e dados cadastrais solicitados.
- O assistente, ao responder a uma nova consulta integrada sobre a validade de uma certificação cuja fonte contém CPF, informa a validade e deixa o CPF fora do rascunho e da versão copiável. O assistente inclui somente os dados específicos que o funcionário autorizar para aquele destinatário.
- O sistema bloqueia a cópia e o envio se o funcionário incluir um CPF ao editar o rascunho e ainda não tiver autorizado o compartilhamento desse dado com o destinatário. O sistema libera a cópia após essa autorização e aplica a RN17 ao envio.
- O sistema só oferece o envio de respostas a mensagens recebidas pela integração quando há um destino válido e o canal permite o envio, conforme a RN17.
- O sistema mostra o destinatário e o canal para o funcionário conferir antes de confirmar. O sistema envia o texto revisado pelo canal de origem após a confirmação explícita do funcionário.
- O sistema bloqueia, antes do disparo, uma resposta que confirma ao comprador o fornecimento de 30 unidades quando as alocações vigentes cobrem apenas 20. O sistema informa o motivo do bloqueio.
- Quando o canal de origem não está integrado, falta um destino válido ou o canal impede o envio, a aplicação informa o motivo e oferece a cópia da resposta conforme a RN21.
- O sistema registra no histórico o texto autorizado, o funcionário que confirmou, o destinatário, o canal e o resultado do envio.
