# Requisitos

## Escopo

O assistente é de uso interno da cooperativa fictícia Sabor da Terra. A aplicação recebe mensagens dos canais integrados para triagem. O assistente analisa as solicitações, responde a consultas internas sobre documentos e dados operacionais com indicação das fontes e prepara resumos por produtor a pedido dos funcionários. Os funcionários escrevem e enviam respostas e notificações pelos canais externos à aplicação.

A equipe consulta os dados e documentos da base fornecida pelo chat. A aplicação permite gerenciar pedidos e registrar alocações de produtores por item do pedido.

A aplicação importa de `lotes.csv` os fornecimentos já confirmados na base. Cada registro gera um lote com data prevista de entrega e fonte identificável.

No cenário do enunciado, a cooperativa recebe de 60 a 100 pedidos por dia por e-mail, formulário web e mensagens de texto. Para a demonstração, a aplicação integra e-mail e WhatsApp.

Os critérios de aceitação estão nas [histórias de usuário](user-stories.md).

## Requisitos funcionais

### RF01 - Conversar com o assistente

O funcionário deve poder conversar com o assistente por texto.

### RF02 - Interpretar pedidos em linguagem natural

O assistente deve interpretar pedidos escritos em linguagem coloquial, em português ou em inglês, com abreviações, erros de digitação, informações implícitas e ambiguidades. A triagem deve ser em português.

regras de negócio:

- O assistente deve interpretar datas relativas a partir da data de recebimento da mensagem em que aparecem.
- O assistente deve pedir esclarecimento quando a data explícita, o dia da semana ou outra referência de prazo entrarem em conflito.

### RF03 - Extrair dados dos pedidos

O assistente deve extrair e organizar produtos, quantidades, unidades, prazos, dados do comprador e condições expressas na mensagem.

regras de negócio:

- O assistente deve apontar as exigências do pedido e, se a mensagem citar um contrato disponível na base, também as exigências do contrato. Para cada exigência, deve indicar a fonte e o que o funcionário ainda precisa conferir.
- O assistente deve preservar a unidade informada e converter quantidades apenas quando houver equivalência conhecida.
- O assistente deve pedir esclarecimento quando a quantidade informada for agregada ou ambígua.

### RF04 - Classificar solicitações na triagem

O assistente deve classificar solicitações por tipo e urgência e sinalizar problemas, como sazonalidade desfavorável e quantidade acima da capacidade de fornecimento documentada.

regras de negócio:

- O assistente deve classificar a intenção principal como pedido, consulta, oferta, comunicado ou não identificado. Cotações e consultas de fornecimento, documentais e financeiras entram como consulta. A análise deve preservar as intenções adicionais da mensagem.
- O assistente deve classificar a solicitação como urgente quando o remetente declarar urgência ou quando houver prazo válido de entrega, resposta ou disponibilização de documentos para o dia do recebimento ou o dia seguinte.
- O assistente deve classificar a urgência como normal quando o primeiro prazo válido for posterior ao dia seguinte ao recebimento e não houver urgência declarada. Se não houver prazo válido nem urgência declarada, deve classificar a urgência como indeterminada.
- O assistente deve usar a data original de recebimento como referência para interpretar o prazo e classificar a urgência. Deve considerar o primeiro dia de um intervalo de entrega ou de um período em que os documentos devam estar disponíveis. Deve indicar na análise quando a data do prazo for anterior à data de recebimento e desconsiderar essa data na classificação.
- O assistente deve registrar na análise o motivo da classificação. Quando o motivo for um prazo, deve indicar a ação solicitada e a data considerada.
- O assistente deve distinguir sazonalidade, capacidade estimada e disponibilidade confirmada. Deve comparar demanda e capacidade em unidades e períodos compatíveis. Estimativas de capacidade e registros de fornecimento não comprovam estoque atual.

### RF05 - Consultar documentos e dados da cooperativa

O assistente deve responder a consultas sobre certificações, rastreabilidade, sazonalidade, lotes e condições de fornecimento presentes nos documentos e dados da cooperativa.

regras de negócio:

- Antes de afirmar que um produto é orgânico, o assistente deve verificar se o certificado cobre o produto e está vigente na data de referência da consulta.
- O assistente deve preservar as unidades dos registros consultados. Para somar quantidades, deve usar a mesma unidade e converter apenas quando houver equivalência conhecida. Quantidades agregadas ou ambíguas exigem esclarecimento antes de entrar nos totais.
- Ao consultar preços e condições, o assistente deve informar a fonte, a vigência e as condições aplicáveis. Deve apontar divergências entre documentos e usar os preços de outubro de 2026 apenas para o período de vigência da tabela.

### RF06 - Identificar as fontes das respostas

O assistente deve identificar as fontes das respostas pelo documento e pelo registro ou trecho pertinente.

regras de negócio:

- Na triagem, o assistente deve indicar de onde vem cada exigência, identificando a mensagem do pedido, o contrato citado ou ambos, conforme o caso.
- Ao informar preços ou condições de fornecimento, o assistente deve associar a fonte ao período de vigência e às condições aplicáveis.
- Ao citar um registro de CSV, o assistente deve identificar o arquivo original e o identificador de origem do registro a partir dos metadados da fonte recuperada. Quando um valor for calculado a partir de vários registros, deve identificar todos os registros usados.
- O sistema deve permitir que o funcionário consulte, pela citação de um CSV, os campos do registro que sustentam a resposta e acesse o arquivo original conforme o RF17.

### RF07 - Informar lacunas e divergências nos dados

O assistente deve informar quando os dados forem ausentes, insuficientes ou conflitantes, sem inventar uma resposta.

regras de negócio:

- Quando a busca não encontrar registros, o assistente deve informar que a informação não foi encontrada, sem concluir que o fato nunca ocorreu.
- Se os documentos apresentarem preços ou condições diferentes, o assistente deve indicar em que divergem.

### RF08 - Gerar resumos por produtor

O assistente deve, quando solicitado, consultar os dados da base para gerar resumos por produtor com vendas, fornecimentos previstos e pendências financeiras.

regras de negócio:

- O sistema deve calcular os valores financeiros do resumo a partir de todos os registros de `financeiro.csv` indexados no RAG que atendam aos critérios de produtor, período e data de referência aplicáveis a cada cálculo.
- O sistema deve selecionar as vendas pela data da transação e os pagamentos pela data registrada de pagamento, dentro do período solicitado.
- O sistema deve incluir nas pendências as vendas feitas até a data de referência cujo pagamento esteja ausente da base ou tenha data posterior à referência. Isso inclui vendas de períodos anteriores.
- O sistema deve distinguir as pendências vencidas das que vencem na data de referência ou depois.
- O assistente deve tratar o pagamento registrado como informação da base, sem usá-lo como comprovação de repasse bancário ao produtor.
- O assistente deve incluir os lotes importados e as alocações operacionais cuja data prevista de entrega caia no período solicitado, incluindo as datas inicial e final. Deve informar a data de cada fornecimento e citar o registro de origem.
- O assistente deve desconsiderar no resumo as alocações operacionais removidas após o cancelamento de um pedido e continuar incluindo os Lotes históricos correspondentes ao período solicitado.
- O assistente deve apresentar os totais de fornecimento previsto por produto e unidade.
- O assistente deve usar conversões de quantidades apenas quando houver equivalência conhecida.
- O assistente deve apresentar quantidades agregadas ou ambíguas como pendências e pedir esclarecimento antes de incluí-las nos totais.
- O sistema deve fornecer ao assistente os resultados dos cálculos e os identificadores das transações financeiras usadas. O assistente deve preservar os valores calculados ao redigir o resumo, conforme o RNF04, e citar os registros que sustentam cada valor financeiro apresentado.

### RF10 - Manter o contexto da conversa

O assistente deve considerar as mensagens e os esclarecimentos anteriores da mesma conversa ao responder ao funcionário, inclusive quando ele reabrir uma conversa salva.

### RF11 - Receber mensagens dos canais integrados

O sistema deve receber mensagens de texto pelos canais integrados.

regras de negócio:

- O sistema deve gerar uma solicitação para cada mensagem nova recebida, inclusive quando ela for uma resposta em uma conversa anterior.
- Ao receber novamente a mesma mensagem, o sistema deve reutilizar a entrada original e manter uma única solicitação para essa entrada.

### RF12 - Exibir cartões na fila de triagem

O sistema deve exibir na fila de triagem um cartão por solicitação com resumo, tipo, estado atual do atendimento e classificação de urgência. O funcionário deve poder consultar o prazo identificado na análise da conversa vinculada, conforme o RF25.

regras de negócio:

- O cartão deve mostrar o tipo da intenção principal e a urgência definidos na triagem.

### RF13 - Esclarecer ambiguidades na triagem

O assistente deve fazer perguntas ao funcionário para esclarecer ambiguidades e atualizar a análise com as respostas, preservando a mensagem original.

regras de negócio:

- Ao pedir esclarecimento sobre uma quantidade agregada ou ambígua, o assistente deve indicar qual informação falta confirmar.
- Ao pedir esclarecimento sobre datas, o assistente deve indicar quais referências entram em conflito, como a data explícita e o dia da semana.

### RF14 - Sugerir produtores para o pedido

O assistente deve sugerir no chat produtores que possam atender ao pedido.

regras de negócio:

- Ao avaliar a certificação orgânica para um fornecimento futuro com prazo conhecido, o assistente deve verificar se o certificado cobre o produto e está vigente na data de entrega ou durante todo o intervalo.
- O assistente deve comparar a demanda com a capacidade em unidades e períodos compatíveis. Na sugestão, deve distinguir sazonalidade, capacidade estimada e disponibilidade confirmada. Estimativas de capacidade e registros de fornecimento não comprovam estoque atual.
- O assistente deve excluir das sugestões os produtores inativos e os incompatíveis com as exigências do pedido ou do contrato citado, quando disponível na base. Deve apresentar separadamente os candidatos aptos e aqueles cuja aptidão ainda precisa ser comprovada.
- Se faltar fornecedor apto ou houver dados insuficientes, o assistente deve explicar o motivo no chat e manter a pendência para decisão do funcionário. Ao sugerir uma alternativa, deve indicar qual item ela substituiria e deixar a decisão com o funcionário.

### RF15 - Atualizar o estado da solicitação

O sistema deve criar cada solicitação no estado recebida, alterar seu estado para em análise quando o funcionário abrir o cartão pela primeira vez e para finalizada quando ele encerrar o atendimento.

regras de negócio:

- O funcionário pode encerrar a solicitação sem atendimento.

### RF16 - Autenticar o acesso do funcionário

O funcionário deve se autenticar para acessar o sistema.

### RF17 - Ler e baixar documentos citados

O funcionário deve poder ler o documento completo e baixar o arquivo original usado na resposta.

### RF18 - Baixar o resumo do produtor em PDF

O sistema deve oferecer a opção "Baixar resumo em PDF" junto a cada resumo por produtor, preservando o conteúdo e as fontes apresentados.

### RF19 - Gerenciar pedidos

O funcionário deve poder criar, consultar, editar e cancelar pedidos.

regras de negócio:

- Ao cancelar um pedido, o sistema deve marcá-lo como cancelado e excluir suas alocações operacionais na mesma operação. O pedido deve continuar disponível para consulta e os Lotes históricos devem ser preservados.
- Antes de salvar uma alteração que invalide alocações operacionais, o sistema deve exigir que o funcionário ajuste ou exclua as alocações afetadas.
- O sistema deve manter o pedido cancelado sem alocações operacionais, inclusive quando o cancelamento e o salvamento de uma alocação ocorrerem em paralelo.

### RF20 - Preparar rascunhos de pedidos no chat

O assistente deve preparar no chat um rascunho de pedido com comprador, itens, quantidades, unidades, prazo e condições de atendimento. O rascunho deve manter a data ou o intervalo de entrega informado pelo comprador. O horário pode ficar nas condições de entrega.

regras de negócio:

- O assistente deve sinalizar no rascunho os itens solicitados sob condição, como "se tiver", para que o funcionário decida quais entram no pedido.

### RF22 - Gerenciar alocações por item do pedido

O funcionário deve poder cadastrar, consultar, editar e excluir alocações operacionais por item do pedido. Cada alocação deve indicar o produtor, a quantidade, a unidade e a data prevista de entrega.

regras de negócio:

- O sistema deve bloquear o cadastro ou a edição de uma alocação para produtor inativo e informar o motivo ao funcionário.
- O funcionário deve confirmar a disponibilidade do produtor para a quantidade, a unidade e a data de entrega antes de salvar a alocação. Se a data mudar, o funcionário deve confirmar novamente a disponibilidade.
- O sistema deve aceitar a data da alocação se ela coincidir com a data única do pedido ou estiver dentro do intervalo de entrega, incluindo os extremos. Se a data estiver fora do prazo, o sistema deve rejeitar a gravação e informar o motivo.
- O sistema deve aceitar apenas quantidades positivas.
- Para somar as alocações, o sistema deve usar a unidade do item e converter quantidades apenas quando houver equivalência conhecida. Deve rejeitar o salvamento se a unidade for incompatível ou se o total ultrapassar a quantidade solicitada.
- O sistema deve aceitar o cadastro ou a edição da alocação apenas se o pedido estiver ativo no momento da gravação.
- O sistema deve validar a alocação no momento da gravação, usando os dados atuais do pedido, do item, do produtor e das demais alocações.

### RF25 - Abrir a conversa da solicitação pelo cartão

O funcionário deve poder abrir, pelo cartão, a conversa vinculada à solicitação. Na conversa, deve poder consultar a análise inicial, as pendências identificadas e o texto original da mensagem recebida, quando houver.

regras de negócio:

- O funcionário deve poder consultar na análise o motivo da classificação de urgência e, quando identificado, o prazo e a ação a que ele se refere.
- O assistente deve apresentar as pendências no chat e indicar o que o funcionário precisa esclarecer, conferir ou decidir. Quando faltar fornecedor apto ou os dados forem insuficientes, deve explicar o motivo da pendência.
- O funcionário deve poder continuar ou finalizar o atendimento mesmo com pendências em aberto.

### RF26 - Indicar o que falta confirmar sobre a disponibilidade

Ao sugerir produtores no chat para atender a um pedido, conforme o RF14, o assistente deve indicar, para cada produtor sugerido, o que o funcionário ainda precisa confirmar sobre o fornecimento proposto.

regras de negócio:

- Na sugestão, o assistente deve distinguir a disponibilidade confirmada da sazonalidade do produto, da capacidade estimada do produtor e do histórico de fornecimento. A sazonalidade, a capacidade estimada e o histórico podem fundamentar a sugestão. A confirmação deve corresponder ao produto, à quantidade e à data propostos.

### RF27 - Considerar o saldo a alocar por item

O assistente deve, ao sugerir atendimento para um pedido cadastrado, obter pelas ferramentas da aplicação o saldo a alocar de cada item e usá-lo na sugestão.

regras de negócio:

- O assistente deve usar o saldo calculado pela quantidade solicitada menos o total das alocações operacionais vigentes daquele item no momento da consulta.
- O assistente deve obter o saldo na unidade do item. Conversões de quantidades alocadas em outras unidades devem ser usadas apenas quando houver equivalência conhecida.

### RF28 - Informar o motivo do bloqueio de exclusão

O sistema deve informar ao funcionário qual vínculo impede a operação quando bloquear uma exclusão.

regras de negócio:

- Quando uma citação impedir a exclusão de um documento, o sistema deve indicar qual citação bloqueia a exclusão.

### RF29 - Disponibilizar documentos após o processamento

O sistema deve disponibilizar os documentos adicionados pela aplicação para consulta e citação pelo assistente após o processamento.

### RF30 - Revisar e editar rascunhos no chat

O funcionário deve poder revisar e editar no chat os rascunhos de pedidos e alocações.

regras de negócio:

- Ao revisar o rascunho de pedido, o funcionário deve decidir quais itens solicitados sob condição serão incluídos.
- Ao revisar o rascunho de alocação, o funcionário deve poder ajustar o pedido, o item, o produtor, a quantidade, a unidade e a data de entrega. A confirmação de disponibilidade deve corresponder aos dados do fornecimento na versão revisada.

### RF31 - Cadastrar pedidos e alocações confirmados no chat

O sistema deve cadastrar a versão revisada do pedido ou da alocação após a confirmação explícita do funcionário no chat.

regras de negócio:

- O sistema deve incluir no pedido somente os itens solicitados sob condição que o funcionário tiver aceitado na revisão.
- O sistema deve usar a mesma operação para cadastrar pedidos pelo chat e pelo cadastro direto. Essa exigência também se aplica ao cadastro de alocações.
- O sistema deve validar a alocação conforme o RF22, considerando as mudanças feitas enquanto o rascunho esteve aberto.
- Se alguma condição impedir o cadastro da alocação, o sistema deve informar o motivo no chat.
- O sistema deve aplicar o RNF03 às confirmações de alocações pelo chat, mantendo uma única alocação ao receber novamente a mesma confirmação.

### RF32 - Vincular o pedido à solicitação de origem

O sistema deve vincular o pedido cadastrado pelo chat da triagem à solicitação de origem. O funcionário deve poder abrir o pedido salvo pelo chat dessa solicitação.

### RF37 - Alertar sobre pedidos de documentos ou dados

O assistente, quando o remetente pedir documentos, dados pessoais ou dados bancários, deve avisar o funcionário e indicar o que foi solicitado.

### RF38 - Gerenciar documentos

O funcionário deve poder listar, adicionar, abrir para leitura, baixar e excluir documentos na aplicação.

regras de negócio:

- O sistema deve bloquear a exclusão de um documento usado em uma citação.

### RF39 - Salvar o prazo de entrega do pedido

O sistema deve salvar o prazo de entrega como data única ou intervalo de datas ao cadastrar ou editar um pedido, conforme definido pelo funcionário.

### RF41 - Carregar o histórico inicial de alocações

O sistema deve importar os lotes de `lotes.csv` como fornecimentos confirmados na base, com a data prevista de entrega registrada no arquivo, e disponibilizá-los para consulta.

regras de negócio:

- A carga deve ser executada por comando explícito durante a preparação inicial do ambiente.
- O sistema deve preservar o identificador original de cada lote no arquivo de origem.
- O sistema deve preservar os dados do produtor, produto, comprador e pedido histórico, a quantidade original e a unidade identificada, as datas de colheita, entrega prevista e validade, a temperatura de transporte, a inspeção visual e as observações.
- A consulta aos registros históricos deve identificar o arquivo e o registro de origem utilizados.
- O sistema deve preservar a referência do pedido histórico quando seu cadastro original estiver ausente da base.
- O sistema deve manter como desconhecidos os dados ausentes, como a quantidade originalmente solicitada e o prazo combinado.
- O sistema deve aplicar o RNF06 à carga dos Lotes, incluindo a preservação dos originais e o tratamento de unidades ambíguas.

### RF42 - Preparar rascunhos de alocações no chat

O assistente deve preparar no chat um rascunho de alocação que identifique o pedido cadastrado, o item, o produtor, a quantidade e a unidade.

regras de negócio:

- O assistente deve mostrar o prazo do pedido, a data prevista para a alocação e a situação da confirmação de disponibilidade.
- O assistente deve pedir esclarecimento antes de oferecer o cadastro quando faltar informação ou houver ambiguidade sobre o pedido, o item, o produtor, a quantidade, a unidade ou a data prevista para a alocação.

### RF46 - Apresentar a alocação cadastrada pelo chat

O sistema deve apresentar no chat a alocação salva e permitir ao funcionário abrir o pedido correspondente para consultá-la.

### RF47 - Recuperar uma triagem antes da criação da solicitação

O funcionário deve poder consultar na seção **Falhas de triagem**, na tela de Triagem, as entradas cuja análise falhou antes da criação de uma solicitação. A aplicação deve mostrar o remetente, o canal e a data de recebimento e oferecer a ação **Tentar triagem novamente**.

- Quando o funcionário pedir uma nova tentativa, a aplicação deve reusar a entrada original, preservar seu texto e sua data de recebimento e indicar o processamento na mesma linha.
- Quando a triagem concluir, a aplicação deve retirar a entrada da seção de falhas e exibir o cartão da solicitação criada. Se a falha se repetir, deve mostrar a falha e voltar a oferecer a ação na mesma entrada.

### Notas gerais

Neste documento, "sistema" e "aplicação" designam o produto completo, que inclui a interface, os serviços e o assistente. As consultas aos registros, os cálculos, as validações e as gravações são executados pelos serviços da aplicação.

O assistente é a parte conversacional do sistema. Ele interpreta mensagens, pede esclarecimentos, apresenta sugestões e redige textos usando os dados e as ferramentas da aplicação. Pode acionar os serviços conforme as condições definidas nos requisitos.

O funcionário esclarece informações, revisa propostas, confirma a disponibilidade dos produtores e autoriza as operações que dependem de sua confirmação.

O lote registra um fornecimento com data prevista de entrega. Na carga, a data vem do CSV. No cadastro operacional, o funcionário confirma a data com o produtor dentro do prazo do pedido. A quantidade originalmente solicitada e o prazo combinado com o comprador dependem de registros que informem esses dados.

As consultas documentais, financeiras e operacionais usam a mesma interface conversacional. Uma mensagem pode exigir várias consultas. A classificação não exige um fluxo ou agente separado para cada tipo.

O funcionário pode discutir as sugestões com o assistente e registrar as alocações na gestão do pedido ou revisar e confirmar um rascunho de alocação no chat.

O assistente apresenta os resumos em texto. O funcionário pode copiá-los.

As regras de implementação das integrações estão em [Integrações](intregracoes.md).

O sistema deve usar o horário local da cooperativa, em Pernambuco, para interpretar datas de mensagens e calcular as datas da triagem.

Quando a consulta não informar uma data de referência, o assistente deve usar a data de recebimento da mensagem de origem ou a data da consulta, se ela tiver começado no chat. Deve informar na resposta qual data usou.

As restrições sanitárias e documentais adotadas pertencem ao cenário simulado.

## Requisitos não funcionais

| ID | Requisito e verificação |
| --- | --- |
| RNF01 | O sistema deve preservar mensagens, conversas, análises, documentos adicionados pela aplicação, pedidos, alocações e Lotes após fechar e reabrir a aplicação. |
| RNF02 | O sistema deve indicar processamento em andamento e avisar sobre a demora após 60 segundos sem conclusão. |
| RNF03 | O sistema deve evitar registros duplicados em novas tentativas da mesma operação, inclusive no recebimento de mensagens, na confirmação pelo chat e no cadastro de alocações. |
| RNF04 | O sistema deve calcular os valores financeiros a partir dos registros selecionados. O assistente deve preservar esses resultados ao redigir a resposta. |
| RNF05 | O sistema deve validar os tokens JWT das consultas e operações internas e rejeitar acessos sem token válido. Antes de processar eventos recebidos por webhook, deve validar sua autenticidade. |
| RNF06 | O sistema deve disponibilizar os dados e documentos fornecidos por uma carga reproduzível, preservando originais, identificadores e fontes. Deve preservar o valor e a descrição originais das quantidades. A unidade usada deve ser a explícita no registro, mesmo quando o nome da coluna indicar outra. O sistema deve sinalizar unidades ambíguas e manter essas quantidades fora de somas e conversões até esclarecê-las. As lacunas da fonte devem ser preservadas. |
| RNF07 | O sistema deve receber mensagens por uma interface comum de entrada, aplicando adaptadores quando necessário. |
| RNF09 | O sistema deve preservar a versão vigente do registro quando rejeitar uma alteração. |
| RNF10 | O sistema deve preservar análises e esclarecimentos mais recentes quando receber resultados atrasados de tentativas anteriores. |
| RNF11 | O sistema deve preservar a solicitação existente para permitir nova tentativa. Se a triagem ainda não tiver criado a solicitação, deve preservar o registro de entrada. Deve oferecer nova tentativa após o aviso de demora. |

## Validação da entrega

Definir os resultados esperados antes de testar as 15 mensagens fornecidas e as consultas das três frentes. Conferir extração, classificação, perguntas de esclarecimento, fontes e reconhecimento de informação ausente ou conflitante.

Na apresentação, executar um script que lê as 15 mensagens de `pedidos.json`, prepara cada registro no formato esperado pela entrada do seu canal e faz uma requisição por mensagem. Verificar se as mensagens entram no fluxo normal de triagem.

Validar as operações dos CRUDs. Verificar o cadastro de um pedido pelo chat e a consulta de uma alocação no resumo por produtor.

Executar a carga inicial dos 20 Lotes de `lotes.csv` e conferir os dados importados, os identificadores originais e as fontes consultadas, conforme a US06.

Consultar LOT-2026-0094 e conferir produtor, produto, quantidade, unidade, data de colheita, data prevista de entrega e referência do pedido histórico. Abrir e baixar o arquivo original pela citação. Consultar LOT-2026-0099 e verificar que a descrição "40 maços (kg)" permanece disponível, com a ambiguidade indicada e a quantidade fora de somas e conversões até esclarecimento.

Gerar o resumo de P004 para setembro de 2026 e conferir as 300 unidades de alface e os 150 maços de coentro com entrega prevista para 08/09/2026. As fontes são LOT-2026-0094 e LOT-2026-0095. Repetir a consulta para os dias 08/09/2026 e 06/09/2026 e conferir os resultados da US07. Verificar os totais por produto e unidade e conferir se o PDF reproduz o conteúdo e as fontes do resumo.

Comparar os valores apresentados pelo assistente no resumo com os resultados retornados pelas ferramentas da aplicação e com os valores esperados a partir dos registros selecionados. Conferir as fontes citadas e verificar que quantidades agregadas ou ambíguas aparecem como pendências, com pedido de esclarecimento, e ficam fora dos totais até serem esclarecidas. Conferir que as conversões usam equivalências conhecidas.

Preparar um rascunho de alocação no chat, editar seus dados, confirmar a disponibilidade e autorizar o cadastro. Conferir a versão salva no chat, na gestão do pedido e no resumo do produtor para o período previsto de entrega. Repetir a mesma confirmação e verificar que existe uma única alocação. Validar os esclarecimentos e os bloqueios previstos na US17, incluindo pedido cancelado, produtor inativo, disponibilidade pendente, quantidade inválida, unidade incompatível, saldo insuficiente e ausência de autenticação válida.

Solicitar uma sugestão de atendimento para um pedido cadastrado e conferir que o assistente usa o saldo de cada item retornado pelas ferramentas da aplicação.

Manter um rascunho de alocação aberto e cadastrar outra alocação que consuma parte desse saldo. Comparar o saldo usado na sugestão com o saldo disponível no momento da gravação. Tentar confirmar uma quantidade superior ao saldo restante e verificar a rejeição com o motivo informado no chat.

Em outro cenário, cancelar o pedido enquanto o rascunho estiver aberto e conferir o bloqueio do cadastro. Verificar que o cancelamento remove as alocações operacionais e preserva os Lotes históricos nas consultas e nos resumos dos respectivos períodos.

Na aplicação publicada na nuvem, testar o recebimento de uma mensagem em cada canal integrado e conferir seu registro e sua análise na triagem. Nos canais que usam webhook, verificar que o sistema rejeita eventos que falham na validação de autenticidade.

Com a equipe desconectada, enviar uma mensagem. Ao voltar à aplicação, verificar que a solicitação está na fila de triagem e que a análise da mensagem está disponível no chat.

Executar os fluxos com um funcionário e a base completa. Medir os tempos de análise e consulta e registrar as condições da demonstração. O limite de espera do RNF02 não representa garantia de conclusão nesse prazo.

## Fora do escopo

- Acesso direto de produtores, compradores e auditores à plataforma.
- Alocações automáticas, controle de estoque e reservas, negociação comercial, acompanhamento de entregas e gestão de pagamentos.