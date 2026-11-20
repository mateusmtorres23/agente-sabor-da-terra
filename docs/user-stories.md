# User stories

O usuário é o funcionário da cooperativa. As referências RF e RNF apontam para [Requisitos](requisitos.md).

## US01 - Acessar a plataforma

Como funcionário, quero me autenticar para consultar informações e trabalhar nas solicitações da cooperativa.

Requisitos: RF16, RNF05.

Critérios de aceitação:

- Credenciais válidas permitem acessar as funções internas.
- Sem autenticação, consultas e alterações internas são rejeitadas.

## US02 - Revisar uma solicitação

Como funcionário, quero receber uma análise da mensagem para entender a demanda e suas pendências antes de decidir.

Requisitos: RF02, RF03, RF04, RF11, RF12, RF15, RF25; RNF03, RNF06, RNF07.

Critérios de aceitação:

- As 15 mensagens enviadas pelo script de apresentação entram na mesma fila e passam pelo mesmo fluxo de triagem que as mensagens dos canais integrados. Reexecutar o script mantém um único registro por mensagem.
- O sistema preserva o texto original, o remetente, o canal e a data de recebimento de cada mensagem, além do identificador de origem quando disponível. Uma nova entrega da mesma mensagem pelo canal integrado mantém um único registro.
- Um comprador envia um pedido de 20 kg de tomate e, enquanto a solicitação está em análise, envia uma nova mensagem em resposta à anterior informando que a entrega pode ser na sexta. A nova mensagem passa por triagem e gera outro cartão. O cartão original preserva a análise e o estado do atendimento. Reentregar a segunda mensagem reaproveita sua entrada e mantém os mesmos dois cartões.
- O sistema, se o Telegram estiver integrado, registra separadamente duas mensagens com o mesmo `message_id` em chats diferentes do mesmo bot. O sistema, ao receber uma reentrega de uma delas, reaproveita apenas o registro do chat correspondente.
- O cartão apresenta resumo, tipo, estado atual do atendimento e classificação de urgência. O funcionário consulta no chat o prazo identificado na análise.
- O funcionário pode abrir o chat pelo cartão para consultar a análise inicial, o motivo da classificação de urgência e o que cada pendência exige esclarecer, conferir ou decidir. Ao voltar à conversa, pode consultar o histórico e, quando houver mensagem recebida, seu texto original.
- A análise organiza os dados extraídos e preserva condições como "se tiver", a frequência de fornecimento e intenções adicionais, como uma oferta acompanhada de solicitação de cadastro.
- O assistente interpreta a mensagem PED-2026-011 em inglês e apresenta a triagem em português.
- Ao abrir o chat do PED-2026-003 em novembro, o funcionário pode consultar 29/10 como a data de entrega interpretada na triagem.
- No PED-2026-015, recebido em 30/10/2026, o cartão mostra **Urgente**. No chat, a análise identifica o prazo de resposta de 31/10/2026 e explica que ele corresponde ao dia seguinte ao recebimento.
- No PED-2026-014, recebido em 30/10/2026, o cartão mostra **Normal**. No chat, a análise indica que os documentos devem estar disponíveis no primeiro dia da inspeção, 11/11/2026, e explica que essa data é posterior ao dia seguinte ao recebimento.

## US03 - Esclarecer ambiguidades

Como funcionário, quero discutir os pontos incertos com o assistente para completar a análise sem adivinhar a intenção do remetente.

Requisitos: RF01, RF07, RF10, RF13.

Critérios de aceitação:

- Produto indefinido, quantidade agregada ou data conflitante gera uma pergunta específica, preservando as informações já compreendidas.
- Quando o remetente usa uma expressão como "amanhã", o assistente calcula a data a partir do recebimento daquela mensagem. Retomar a conversa em outro dia não altera a interpretação.
- O assistente registra o esclarecimento na conversa e atualiza a análise, a sugestão e os alertas afetados, preservando a mensagem original.
- Perguntas de acompanhamento usam o contexto daquela conversa, sem incorporar dados de outra solicitação.

## US04 - Avaliar uma sugestão de atendimento

Como funcionário, quero conhecer os produtores candidatos para comparar alternativas de atendimento.

Requisitos: RF03, RF06, RF14, RF22, RF26, RF27, RF30, RF31, RF42.

Critérios de aceitação:

- A sugestão identifica os produtores candidatos e cita as fontes usadas.
- O assistente indica o que o funcionário ainda precisa confirmar sobre a disponibilidade dos produtores sugeridos.
- Para um pedido cadastrado, o assistente usa na sugestão o saldo de cada item obtido pelas ferramentas da aplicação.
- O saldo corresponde à quantidade solicitada menos o total das alocações operacionais vigentes do item no momento da consulta. O cálculo usa a unidade do item e converte quantidades apenas quando houver equivalência conhecida.
- O assistente exclui produtores inaptos da sugestão e indica o motivo. O assistente apresenta dados ausentes ou conflitantes como pendências e indica a aptidão sem comprovação como pendente, separada dos candidatos aptos.
- Na triagem do PED-2026-004, se a base só informar o número do DAP ou CAF, o assistente aponta que falta comprovar a vigência e cita o contrato do PNAE.
- O funcionário pode discutir alternativas no chat e registrar as alocações escolhidas na gestão do pedido ou revisar e confirmar um rascunho de alocação no chat.

## US05 - Acompanhar a triagem

Como funcionário, quero consultar a situação das solicitações para identificar o que ainda depende de decisão.

Requisitos: RF12, RF15, RF25.

Critérios de aceitação:

- Na fila de triagem, o funcionário vê o estado atual de cada solicitação. As pendências ficam disponíveis no chat da solicitação.
- Uma solicitação nova aparece como `recebida`. Quando o funcionário abre o cartão pela primeira vez, o sistema muda o estado para `em análise`.
- Se faltar fornecedor apto, o assistente explica o motivo no chat. Mesmo com essa pendência em aberto, o funcionário pode continuar o atendimento para buscar esclarecimentos ou encerrar sem atendimento.
- Quando o funcionário encerra o atendimento, o sistema muda o estado da solicitação para `finalizada`.

## US06 - Consultar documentos e dados

Como funcionário, quero fazer perguntas sobre os registros da cooperativa para responder às demandas com fontes verificáveis.

Requisitos: RF01, RF05, RF06, RF07, RF17, RF41; RNF06.

Critérios de aceitação:

- A consulta pode combinar documentos e dados operacionais na mesma conversa.
- Em uma consulta iniciada no chat sem data informada, o assistente usa a data da consulta e a indica na resposta.
- A resposta identifica documentos e registros ou trechos que sustentam as afirmações. Consultas sobre certificação verificam validade e produto coberto; consultas sobre lote identificam sua origem registrada.
- Após a carga de `lotes.csv`, os 20 Lotes ficam disponíveis para consulta com seus identificadores originais e os dados fornecidos de produtor, produto, comprador, pedido histórico, quantidade, unidade identificada, datas, temperatura de transporte, inspeção visual e observações.
- A consulta ao LOT-2026-0094 informa o fornecimento confirmado de 300 unidades de alface de P004, com colheita em 06/09/2026 e entrega prevista para 08/09/2026. A resposta informa a referência PED-2026-SEP-008 e identifica a fonte como `lotes.csv - LOT-2026-0094`.
- A referência PED-2026-SEP-008 permanece disponível quando o pedido original estiver ausente da base. A quantidade originalmente solicitada e o prazo combinado são apresentados como desconhecidos quando faltarem registros que os comprovem.
- No LOT-2026-0099, o assistente preserva a descrição "40 maços (kg)", indica a unidade ambígua e deixa a quantidade fora de somas e conversões até esclarecimento.
- Preços informam vigência e condições. Informação ausente ou conflitante é explicitada, sem completar a resposta por suposição.
- A citação permite ler o documento completo na plataforma e baixar o arquivo original usado na resposta.
- Ao abrir a citação de `lotes.csv - LOT-2026-0094`, o funcionário pode conferir no registro citado o produtor, o produto, a quantidade e as datas usadas na resposta, além de abrir e baixar o CSV original. Ao reabrir o chat, a citação permanece vinculada à mesma resposta, ao mesmo registro e ao arquivo original.

## US07 - Consultar e baixar o resumo de um produtor

Como funcionário, quero gerar e baixar em PDF um resumo das vendas, dos fornecimentos previstos e das pendências financeiras de um produtor.

Requisitos: RF06, RF08, RF18, RF22, RF41; RNF04, RNF06.

Critérios de aceitação:

- O resumo identifica produtor, período e data de referência, com fontes dos valores e registros apresentados.
- O resumo combina os resultados financeiros calculados pela aplicação com os Lotes e as alocações operacionais do produtor, conforme o RF08. A ferramenta consulta todos os registros de `financeiro.csv` indexados que atendam aos critérios de cada cálculo. O resumo apresenta os valores retornados pela ferramenta e os identificadores das transações que os sustentam.
- Os valores financeiros calculados pela aplicação e apresentados pelo assistente correspondem aos valores esperados a partir dos registros de origem selecionados.
- O resumo usa a data da transação para selecionar vendas e a data de pagamento para selecionar pagamentos registrados. No resumo da produtora P001 para setembro de 2026, as vendas totalizam R$ 1.090,00 a partir de `FIN-2026-001`, `FIN-2026-002` e `FIN-2026-015`. Os pagamentos registrados em setembro somam R$ 150,00 de `FIN-2026-015`. Os R$ 940,00 de `FIN-2026-001` e `FIN-2026-002` entram nos pagamentos registrados em outubro. As quantidades respeitam produto e unidade.
- O resumo distingue pendências vencidas e a vencer na data de referência, inclusive as de períodos anteriores. Quando não encontra registros, o assistente informa a ausência. O pagamento registrado, por si só, não comprova repasse bancário.
- No resumo da produtora P001 com referência em 30/09/2026, os R$ 940,00 de `FIN-2026-001` e `FIN-2026-002` aparecem como valor a vencer em 02/10/2026. O CSV registra o pagamento em 01/10/2026.
- No resumo de P004 para setembro de 2026, com referência em 30/09/2026, aparecem R$ 1.020,00 em vendas e R$ 1.020,00 a vencer em 23/10/2026. O resumo e o PDF associam ambos os valores a `financeiro.csv - FIN-2026-006` e `financeiro.csv - FIN-2026-007`.
- O resumo inclui os lotes importados e as alocações operacionais cuja data prevista de entrega esteja no período solicitado. Mostra a data de cada fornecimento e os totais por produto e unidade. Quantidades ambíguas aparecem como pendências e ficam fora dos totais até esclarecimento.
- O assistente pede esclarecimento sobre quantidades agregadas ou ambíguas antes de incluí-las nos totais. As conversões de quantidades usadas no resumo dependem de equivalência conhecida.
- O resumo de P004 para setembro de 2026 apresenta 300 unidades de alface e 150 maços de coentro com entrega prevista para 08/09/2026, citando LOT-2026-0094 e LOT-2026-0095 de `lotes.csv`.
- O resumo de P004 para 08/09/2026 inclui esses dois lotes. Para 06/09/2026, data da colheita, informa que a base não contém fornecimentos com entrega prevista para aquele dia.
- Para um pedido com prazo de 4 a 8 de novembro e um lote com entrega prevista para o dia 6, o resumo inclui o lote na consulta do dia 6 e o exclui da consulta do dia 5.
- Após o cancelamento de um pedido, as alocações operacionais removidas deixam de aparecer nos novos resumos. Os Lotes históricos continuam disponíveis nos resumos dos respectivos períodos.
- O resumo é acompanhado da opção "Baixar resumo em PDF". O arquivo preserva o conteúdo e as fontes exibidos.

## US08 - Retirada do escopo

A história de preparar e enviar notificações a produtores foi retirada do projeto. Os funcionários escrevem e enviam essas notificações pelos canais externos.

## US09 - Retomar o trabalho

Como funcionário, quero reencontrar as solicitações e suas conversas para continuar a triagem após sair da aplicação.

Requisitos: RF10; RNF01.

Critérios de aceitação:

- Após reabrir a aplicação e se autenticar, o funcionário encontra mensagens, análises, conversas, documentos adicionados, pedidos, alocações e Lotes.
- Ao retomar uma conversa, o assistente considera seus esclarecimentos anteriores e mantém o contexto separado das demais solicitações.

## US10 - Recuperar uma operação com falha

Como funcionário, quero saber quando uma operação falhou e poder tentar novamente para continuar o atendimento.

Requisitos: RF02, RF25, RF47; RNF02, RNF03, RNF09 a RNF11.

Critérios de aceitação:

- A interface indica processamento e informa falhas. Após 60 segundos sem conclusão, informa a demora.
- O sistema oferece nova tentativa após o aviso de demora.
- Se a triagem falhar antes de criar o cartão, a tela de Triagem mostra a entrada na seção **Falhas de triagem** com remetente, canal e data de recebimento. Ao clicar em **Tentar triagem novamente**, o funcionário vê a mesma linha indicar processamento.
- Após uma falha, tentar novamente a triagem de uma mensagem recebida em 30/10 que dizia “amanhã” usa o texto e a data originais, mesmo que a tentativa ocorra em 21/11. Se a análise concluir, a linha sai da seção e a fila mostra um único cartão. Ao abri-lo, o funcionário consulta no chat o prazo de 31/10. Se a falha se repetir, a mesma entrada volta a oferecer nova tentativa.
- Se dois funcionários clicarem em **Tentar triagem novamente** ao mesmo tempo para a mesma entrada, a aplicação inicia uma única nova tentativa.
- Se a solicitação já tiver sido criada, ela permanece disponível após uma falha na triagem.
- Falhas do modelo e das consultas são informadas na interface e preservam a solicitação ou a entrada registrada para nova tentativa, conforme o RNF11.
- Repetir a mesma operação mantém um único registro, inclusive na confirmação de pedidos pelo chat e no cadastro de alocações.
- Uma alteração rejeitada mantém o registro anterior.
- O resultado atrasado de uma tentativa anterior não substitui análises ou esclarecimentos mais recentes.

## US11 - Gerenciar documentos

Como funcionário, quero gerenciar os documentos da base para que o assistente possa consultá-los e citá-los nas respostas.

Requisitos: RF28, RF29, RF38; RNF01, RNF05, RNF06.

Critérios de aceitação:

- O funcionário pode adicionar um documento, encontrá-lo na lista, abrir seu conteúdo e baixar o arquivo com o nome original.
- O sistema só exibe o documento na lista depois de gravar o arquivo e salvar o registro.
- O funcionário pode adicionar dois documentos com o mesmo nome. Em cada registro, pode abrir e baixar o arquivo correspondente.
- O funcionário pode excluir um documento sem citações. O sistema remove o arquivo e retira o documento da lista.
- O sistema bloqueia a exclusão de um documento citado, preserva o registro e o arquivo e informa ao funcionário qual citação impede a operação.
- O assistente pode consultar e citar o documento adicionado após o processamento.

## US12 - Gerenciar pedidos

Como funcionário, quero gerenciar os pedidos da cooperativa para acompanhar as demandas cadastradas.

Requisitos: RF19, RF39.

Critérios de aceitação:

- O funcionário pode criar, consultar, editar e cancelar pedidos.
- No cadastro manual e na edição, o funcionário pode informar uma data ou um intervalo de entrega. O pedido salvo mostra o prazo informado.
- No cadastro manual e na edição, o funcionário pode informar as condições de atendimento. Ao consultar o pedido salvo, ele vê o texto que confirmou.
- A aplicação registra o cancelamento e exclui as alocações operacionais do pedido na mesma operação. O pedido continua consultável com o estado cancelado e os Lotes históricos são preservados.

## US13 - Cadastrar um pedido pelo chat

Como funcionário, quero revisar e confirmar um pedido no chat para registrá-lo na gestão de pedidos.

Requisitos: RF19, RF20, RF30 a RF32, RF39; RNF03.

Critérios de aceitação:

- O assistente apresenta no chat um rascunho com o comprador, os itens, as quantidades, as unidades, o prazo e as condições de atendimento.
- Se o comprador pedir entrega de 4 a 8 de novembro, o rascunho mostra o intervalo e o sistema o salva ao confirmar o pedido. Se o funcionário escolher um dia específico na revisão, o sistema salva a data escolhida.
- Ao revisar o rascunho no chat, o funcionário pode ajustar os dados e decidir se inclui os itens solicitados sob condição.
- Se o funcionário ajustar a quantidade de 30 para 15 durante a revisão e confirmar o rascunho, o pedido é salvo com a quantidade 15.
- Após a confirmação explícita do funcionário, o sistema cadastra a versão revisada. O pedido fica disponível para consulta e edição na gestão de pedidos.
- Quando o pedido é cadastrado pela triagem, o funcionário pode abri-lo pelo chat da solicitação de origem, inclusive depois de reabrir a conversa.
- Ao consultar o pedido cadastrado a partir do PED-2026-004, o funcionário encontra a exigência de certificação orgânica para o mel no texto salvo das condições.

## US15 - Gerenciar alocações

Como funcionário, quero gerenciar as alocações operacionais de cada item do pedido para registrar quem atenderá a demanda.

Requisitos: RF19, RF22.

Critérios de aceitação:

- O funcionário pode cadastrar, consultar, editar e excluir alocações operacionais. Cada alocação identifica o item do pedido, o produtor, a quantidade, a unidade e a data prevista de entrega.
- O sistema exige pedido ativo e disponibilidade confirmada pelo funcionário para cadastrar ou editar uma alocação. Se a data da alocação mudar, o funcionário confirma novamente a disponibilidade.
- Para um pedido com entrega de 4 a 8 de novembro, o sistema aceita uma alocação para o dia 4 ou 8 e rejeita o dia 9 com o motivo. Para um pedido com data única, aceita somente essa data.
- A quantidade alocada é positiva. O sistema converte as quantidades para a unidade do item antes de verificar se a soma respeita o limite solicitado. Se a unidade for incompatível ou o total ultrapassar o limite, o sistema rejeita o salvamento.
- Se o funcionário tentar cadastrar ou editar uma alocação para o produtor P015, marcado como inativo na base, o sistema impede o salvamento e informa o motivo.
- O funcionário precisa ajustar ou excluir as alocações operacionais afetadas antes de salvar uma alteração do pedido que entre em conflito com elas.
- O sistema rejeita o salvamento de uma alocação após o cancelamento do pedido, mesmo se o formulário tiver sido aberto antes. O sistema mantém o pedido cancelado sem alocações operacionais mesmo se o salvamento e o cancelamento forem simultâneos e preserva os Lotes históricos.

## US16 - Identificar pedidos de documentos ou dados

Como funcionário, quero identificar quais documentos, dados pessoais ou dados bancários o remetente pediu para decidir como conduzir o atendimento.

Requisitos: RF37.

Critérios de aceitação:

- Quando o remetente pede documentos, dados pessoais ou dados bancários, o assistente avisa o funcionário na análise e indica o que foi solicitado.
- Na análise do PED-2026-009, o aviso lista as certificações, as fichas técnicas e os dados cadastrais dos produtores pedidos pelo remetente.

## US17 - Cadastrar uma alocação pelo chat

Como funcionário, quero revisar e confirmar uma alocação no chat para registrar quem atenderá um item do pedido.

Requisitos: RF22, RF27, RF30, RF31, RF42, RF46; RNF01, RNF03, RNF05.

Critérios de aceitação:

- O assistente apresenta no chat um rascunho com pedido cadastrado, item, produtor, quantidade e unidade. O rascunho mostra o prazo do pedido, a data prevista para a alocação e a situação da confirmação de disponibilidade.
- Quando faltar informação ou houver ambiguidade no pedido, item, produtor, quantidade, unidade ou data prevista para a alocação, o assistente pede esclarecimento antes de oferecer o cadastro.
- O funcionário pode ajustar o pedido, o item, o produtor, a quantidade, a unidade e a data da alocação antes de confirmar. A confirmação de disponibilidade corresponde aos dados do fornecimento na versão revisada.
- O sistema cadastra a versão revisada após a confirmação explícita do funcionário e usa a mesma operação e as mesmas validações do cadastro direto de alocações.
- O sistema rejeita o cadastro e informa o motivo no chat quando o pedido estiver cancelado, o produtor estiver inativo, a disponibilidade estiver pendente, a quantidade for inválida, a unidade for incompatível, a data estiver fora do prazo do pedido ou o total ultrapassar a quantidade solicitada.
- Se outras alocações consumirem o saldo enquanto o rascunho estiver aberto, o sistema verifica o saldo atual na gravação e rejeita o cadastro que ultrapassar o limite. O sistema também rejeita o cadastro se o pedido tiver sido cancelado nesse intervalo.
- Após cadastrar a alocação, o sistema a apresenta no chat e permite abrir o pedido correspondente. O funcionário pode consultar e editar a alocação pela gestão do pedido.
- Repetir a mesma confirmação mantém uma única alocação cadastrada.
- Após reabrir a aplicação, o funcionário pode consultar a alocação salva. Ela aparece nos resumos do produtor conforme o período previsto de entrega.
- O sistema rejeita o cadastro sem autenticação válida.
