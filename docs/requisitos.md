# Requisitos

## Escopo

O assistente é de uso interno da cooperativa fictícia Sabor da Terra. Ele analisa as solicitações que entram na triagem, responde a consultas sobre documentos e dados operacionais com indicação das fontes e prepara resumos e notificações para produtores a pedido dos funcionários. Os funcionários conduzem o atendimento a compradores, produtores e auditores e autorizam as respostas e notificações antes do envio pela aplicação.

A aplicação também permite à equipe manter os cadastros de produtores, produtos e documentos, gerenciar pedidos e agendamentos semanais e registrar alocações de produtores por item do pedido.

No cenário do enunciado, a cooperativa recebe de 60 a 100 pedidos por dia por e-mail, formulário web e mensagens de texto. Para a demonstração, a aplicação integra e-mail e WhatsApp, com Telegram como alternativa ao WhatsApp.

Os critérios de aceitação estão nas [histórias de usuário](user-stories.md).

## Requisitos funcionais

| ID | Requisito |
| --- | --- |
| RF01 | O funcionário deve poder conversar com o assistente por texto. |
| RF02 | O assistente deve interpretar pedidos escritos em linguagem coloquial, em português ou em inglês, com abreviações, erros de digitação, informações implícitas e ambiguidades. A triagem deve ser em português. |
| RF03 | O assistente deve extrair e organizar produtos, quantidades, unidades, prazos, dados do comprador e condições expressas na mensagem. |
| RF04 | O assistente deve classificar solicitações por tipo e urgência e sinalizar problemas, como sazonalidade desfavorável e quantidade acima da capacidade de fornecimento documentada. |
| RF05 | O assistente deve responder a consultas sobre certificações, rastreabilidade, sazonalidade, lotes e condições de fornecimento presentes nos documentos e dados da cooperativa. |
| RF06 | O assistente deve identificar as fontes das respostas pelo documento e pelo registro ou trecho pertinente. |
| RF07 | O assistente deve informar quando os dados forem ausentes, insuficientes ou conflitantes, sem inventar uma resposta. |
| RF08 | O assistente deve, quando solicitado, gerar resumos por produtor com vendas, pedidos alocados e pendências financeiras. |
| RF09 | O assistente deve redigir, quando solicitado, notificações para produtores sobre pedidos de seus produtos. |
| RF10 | O assistente deve manter o contexto de cada conversa, inclusive quando o funcionário retomar o trabalho em outra sessão. |
| RF11 | O sistema deve receber mensagens de texto pelos canais integrados. |
| RF12 | O sistema deve apresentar cada solicitação em um cartão com resumo, classificação e pendências. |
| RF13 | O assistente deve fazer perguntas ao funcionário para esclarecer ambiguidades e atualizar a análise com as respostas, preservando a mensagem original. |
| RF14 | O assistente deve sugerir no chat produtores que possam atender ao pedido. |
| RF15 | O sistema deve mostrar o estado de cada solicitação na fila de triagem. A solicitação entra como recebida e passa para em análise quando o assistente começa a analisá-la. Ao concluir ou atualizar a análise, o sistema deve marcar a solicitação como aguardando informações se faltar algum dado para decidir ou como pronta para decisão se já for possível decidir, inclusive quando o atendimento for inviável. O funcionário decide quando encerrar a solicitação. No encerramento, o sistema deve registrar o resultado da triagem e as pendências restantes. |
| RF16 | O funcionário deve se autenticar para acessar o sistema. |
| RF17 | O funcionário deve poder ler o documento completo e baixar o arquivo original usado na resposta. A citação continua apontando para esse arquivo após a substituição do documento no cadastro. |
| RF18 | O sistema deve oferecer a opção "Baixar resumo em PDF" junto a cada resumo por produtor, preservando o conteúdo e as fontes apresentados. |
| RF19 | O funcionário deve poder cadastrar, consultar, editar e excluir registros de produtores, produtos e documentos. |
| RF20 | O funcionário deve poder criar, consultar, editar e cancelar pedidos. O sistema deve salvar o prazo de entrega como data única ou intervalo de datas, conforme o funcionário confirmar. |
| RF21 | O assistente deve preparar no chat um rascunho de pedido com comprador, itens, quantidades, unidades, prazo e condições de atendimento. O rascunho deve manter a data ou o intervalo de entrega informado pelo comprador. O horário pode ficar nas condições de entrega. |
| RF22 | O funcionário deve poder cadastrar, consultar, editar e cancelar agendamentos semanais. |
| RF23 | O funcionário deve poder cadastrar, consultar, editar e excluir alocações por item do pedido. Cada alocação deve indicar o produtor, a quantidade e a unidade. |
| RF24 | O assistente, a pedido do funcionário, deve preparar um rascunho de resposta ao remetente. |
| RF25 | O sistema, ao salvar um agendamento semanal, deve registrar o comprador, os itens, as quantidades, as unidades, as condições de atendimento confirmadas pelo funcionário, a primeira data de fornecimento e a antecedência da triagem em dias corridos. |
| RF26 | O sistema deve usar o mesmo fluxo de triagem para as mensagens dos canais integrados e as mensagens da amostra. |
| RF27 | O sistema deve preservar o texto original, o remetente, o canal e a data de recebimento de cada mensagem, além do identificador de origem quando disponível. |
| RF28 | O sistema deve marcar na lista de triagem as mensagens da amostra. |
| RF29 | O funcionário deve poder abrir o chat da solicitação a partir do cartão. No chat, deve poder consultar a análise inicial do assistente, o histórico da conversa e o texto original das mensagens recebidas, quando houver. |
| RF30 | O assistente, ao sugerir um produtor, deve informar a capacidade estimada para o produto quando houver dados suficientes. A sugestão deve indicar a unidade, o período e a fonte da estimativa. |
| RF31 | O assistente deve indicar na sugestão o que o funcionário ainda precisa confirmar sobre a disponibilidade do produtor. |
| RF32 | Ao sugerir atendimento para um pedido cadastrado, o assistente deve considerar, para cada item, a quantidade solicitada menos a quantidade já alocada. |
| RF33 | Ao bloquear uma exclusão, o sistema deve informar ao funcionário qual vínculo impede a operação. |
| RF34 | O assistente deve usar os dados atuais dos cadastros nas consultas e sugestões de atendimento. |
| RF35 | Ao salvar um pedido, o sistema deve registrar cada condição de atendimento que o funcionário confirmou e indicar se ela vale para todo o pedido ou para itens específicos. |
| RF37 | O funcionário deve poder revisar e editar no chat os rascunhos de pedidos e agendamentos. |
| RF38 | O sistema deve cadastrar a versão revisada do pedido ou do agendamento após a confirmação explícita do funcionário no chat. Para pedidos, deve usar a mesma operação do cadastro direto. Quando o cadastro do pedido partir da triagem, o sistema deve vinculá-lo à solicitação de origem e permitir que o funcionário abra o pedido pelo chat dessa solicitação. |
| RF39 | O assistente deve preparar no chat um rascunho de agendamento semanal com os campos definidos no RF25. |
| RF40 | O funcionário deve poder editar o texto dos rascunhos de respostas e notificações e copiá-lo conforme a RN21. |
| RF41 | O sistema, quando o envio estiver disponível, deve mostrar o destinatário e o canal para o funcionário conferir antes de confirmar. |
| RF42 | O sistema deve registrar no histórico o texto autorizado, o funcionário que confirmou o envio, o destinatário, o canal e o resultado do envio. |
| RF43 | O assistente, quando o remetente pedir documentos, dados pessoais ou dados bancários, deve avisar o funcionário e indicar o que foi solicitado. |

As consultas documentais, financeiras e operacionais usam a mesma interface conversacional. Uma mensagem pode exigir várias consultas. A classificação não exige um fluxo ou agente separado para cada tipo.

O funcionário pode discutir as sugestões com o assistente no chat. Ele decide e registra as alocações na gestão do pedido.

O assistente apresenta os resumos e as notificações em texto. O funcionário pode copiá-los.

O Telegram pode substituir o WhatsApp na demonstração se o teste com a integração da Meta não atender ao fluxo previsto. As opções de implementação estão em [Integrações](intregrations.md).

## Regras de negócio

| ID | Regra |
| --- | --- |
| RN01 | O assistente deve verificar se o certificado cobre o produto e está vigente na data de referência antes de afirmar que o produto é orgânico. Para fornecimento futuro com prazo conhecido, deve conferir a validade na data prevista ou durante todo o intervalo de entrega. |
| RN02 | O assistente deve apontar na triagem as exigências do pedido. Se a mensagem citar um contrato disponível na base, deve apontar também as exigências do contrato. Em cada caso, deve informar a fonte e o que o funcionário ainda precisa conferir. |
| RN03 | Preservar unidades e converter apenas com equivalência conhecida. Quantidades agregadas ou ambíguas exigem esclarecimento. Valores em kg, maços, unidades e dúzias não podem ser somados como uma única medida. |
| RN04 | Distinguir sazonalidade, capacidade estimada e disponibilidade confirmada. Comparar quantidades apenas com unidades e períodos compatíveis. Capacidade e entregas anteriores não comprovam estoque atual. |
| RN05 | Ao consultar preços e condições, informar a fonte, o período de vigência e as condições aplicáveis. Expor divergências entre documentos. Preços de outubro de 2026 não comprovam preços de outros períodos. |
| RN06 | Interpretar datas relativas pela data de recebimento da mensagem em que aparecem. Pedir esclarecimento quando data explícita, dia da semana ou outras referências se contradisserem. |
| RN07 | Classificar como pedido de compra, cotação ou consulta de fornecimento, consulta documental, consulta financeira, oferta de produtor, comunicação administrativa ou não identificado. Preservar intenções adicionais da mesma mensagem. |
| RN08 | O assistente deve indicar o motivo da urgência quando ela for declarada ou quando a entrega estiver prevista para o dia do recebimento ou o seguinte. Para um intervalo de entrega, deve usar o primeiro dia para classificar a urgência. Deve classificar como normal quando o prazo for posterior e não houver urgência declarada, ou como indeterminada quando faltarem dados. Na fila, o sistema deve sinalizar o vencimento separadamente assim que a data de entrega ou o último dia do intervalo tiver passado. |
| RN09 | O sistema deve apurar as vendas pela data da transação e os pagamentos pela data registrada de pagamento, dentro do período solicitado. O resumo inclui uma alocação se a data de entrega cair no período ou se o intervalo de entrega tiver pelo menos um dia nele. Para apurar as pendências, o sistema deve incluir as vendas feitas até a data de referência cujo pagamento não conste na base ou tenha data posterior à referência, inclusive vendas de períodos anteriores. Deve separar as vencidas das que vencem na data de referência ou depois. O registro de pagamento não comprova repasse bancário ao produtor. |
| RN10 | Sem fornecedor apto ou dados suficientes, apresentar o motivo e manter a pendência para decisão do funcionário. Alternativas não podem substituir silenciosamente os itens solicitados. O funcionário pode encerrar a solicitação sem atendimento. |
| RN11 | O sistema só deve considerar válido um compromisso de fornecimento se o pedido estiver ativo e as alocações vigentes cobrirem os itens, as quantidades, as unidades e os prazos prometidos. O sistema deve conferir as alocações do produtor destinatário da notificação e dos produtores que o texto identificar como responsáveis pelo compromisso. Para fornecimento futuro, deve verificar se esses produtores continuam ativos e se a comprovação das exigências da RN02, quando aplicável aos produtores ou aos itens alocados, é válida na data prometida ou durante todo o intervalo prometido. |
| RN12 | O sistema deve bloquear o cadastro ou a edição de uma alocação se o produtor estiver marcado como inativo e informar o motivo ao funcionário. |
| RN13 | O sistema deve aceitar apenas quantidades positivas nas alocações. Deve somar as alocações na unidade do item, usando apenas as conversões permitidas pela RN03, e rejeitar o salvamento se a unidade for incompatível ou o total ultrapassar a quantidade solicitada. |
| RN14 | O sistema, ao cancelar um pedido, deve mudar seu estado para cancelado e excluir suas alocações na mesma operação. O sistema deve manter o pedido disponível para consulta e retirar essas alocações dos próximos resumos do produtor. |
| RN15 | O sistema deve gerar uma única solicitação por ocorrência na data prevista para a triagem e vinculá-la ao agendamento. A solicitação deve registrar o comprador, os itens, as quantidades, as unidades, as condições de atendimento e a data de fornecimento. O sistema deve aplicar alterações e cancelamentos da série apenas às ocorrências pendentes. Se o dia de fornecimento mudar, o novo dia passa a valer a partir da semana de fornecimento da primeira ocorrência pendente. A semana vai de segunda a domingo. Se a série já tiver uma solicitação com fornecimento naquela semana, a mudança começa na semana seguinte. As solicitações já geradas mantêm os dados originais. |
| RN16 | Acrescentar a resposta ao histórico da solicitação aberta quando houver vínculo confiável e atualizar a análise e as pendências. Se uma resposta vinculada corrigir um dado usado em um rascunho de pedido aberto, mostrar a correção ao funcionário antes da confirmação. O funcionário decide se ajusta o rascunho. O mesmo remetente ou a mesma conversa, por si só, não estabelece esse vínculo. Iniciar nova triagem para demandas independentes, vínculos incertos ou respostas a solicitações encerradas. |
| RN17 | O sistema deve oferecer apenas revisão e cópia do rascunho para respostas às mensagens da amostra. O sistema deve enviar somente a versão do texto que o funcionário confirmou explicitamente para o destinatário e o canal conferidos. O sistema deve enviar respostas pelo canal de origem se a mensagem tiver chegado por um canal integrado, houver um destino válido e o canal permitir o envio. O sistema deve enviar notificações pelo canal integrado escolhido pelo funcionário e para o destino conferido na revisão. Na demonstração, deve restringir o envio de notificações a destinos de teste vinculados pela equipe ao produtor. Quando o envio estiver indisponível, o sistema deve informar o motivo e oferecer a cópia do rascunho conforme a RN21. |
| RN18 | O sistema só deve permitir nova tentativa de envio após confirmar a falha anterior e receber nova confirmação explícita do funcionário. O sistema deve manter o reenvio bloqueado enquanto houver uma tentativa em andamento ou com resultado incerto, mesmo se o funcionário editar o rascunho. O sistema deve sinalizar resultados incertos para conferência. |
| RN19 | O sistema deve bloquear a exclusão de um registro de produtor, produto ou documento vinculado a um pedido, alocação, agendamento, lote, transação financeira ou citação. |
| RN20 | O funcionário deve decidir se inclui no pedido cada item solicitado sob condição, como "se tiver". |
| RN21 | O assistente deve deixar fora dos rascunhos externos, por padrão, documentos internos, documentos solicitados pelo remetente e dados pessoais ou bancários. O sistema só deve disponibilizar para cópia ou envio um texto com esse material depois que o funcionário autorizar os dados ou trechos específicos para aquele destinatário. |
| RN22 | O sistema, na confirmação pelo funcionário e imediatamente antes de cada tentativa de envio, deve aplicar a RN11 às respostas e notificações que confirmam fornecimento. O sistema deve bloquear o envio e informar o motivo se o compromisso não atender à regra. |
| RN23 | O assistente deve excluir das sugestões os produtores inativos ou incompatíveis com as exigências da RN02. O assistente deve mostrar a aptidão ainda sem comprovação como pendente, separada dos candidatos aptos. |
| RN24 | O funcionário deve confirmar a disponibilidade para o fornecimento antes de salvar uma alocação. |
| RN25 | O sistema deve exigir que o funcionário ajuste ou exclua as alocações afetadas antes de salvar uma alteração do pedido que as invalide. |
| RN26 | O sistema só deve salvar o cadastro ou a edição de uma alocação se o pedido estiver ativo no momento da gravação. O sistema deve garantir que o pedido cancelado fique sem alocações mesmo quando o salvamento e o cancelamento ocorrerem em paralelo. |
| RN27 | O sistema, ao retomar o serviço ou salvar um agendamento novo ou editado, deve verificar as ocorrências pendentes cuja triagem está prevista para hoje ou antes. O sistema deve gerar a solicitação imediatamente se o fornecimento for hoje ou depois. O sistema deve marcar a ocorrência como perdida e seguir com a próxima se a data de fornecimento já passou. |

O sistema deve usar o horário local da cooperativa, em Pernambuco, para interpretar datas de mensagens e calcular as datas da triagem e dos agendamentos. Quando a consulta não trouxer uma data de referência, o assistente deve usar a data de recebimento da mensagem de origem ou a data da consulta, se ela tiver começado no chat. Deve informar na resposta qual data usou. A ausência de registros deve ser apresentada como informação não encontrada, sem concluir que o fato nunca ocorreu. As restrições sanitárias e documentais adotadas pertencem ao cenário simulado.

## Requisitos não funcionais

| ID | Requisito e verificação |
| --- | --- |
| RNF01 | Preservar mensagens, histórico de envios, conversas, análises, cadastros, pedidos, agendamentos e alocações após fechar e reabrir a aplicação. Verificar que a retomada mantém os dados e separa o contexto de cada solicitação. |
| RNF02 | O sistema deve indicar processamento em andamento e avisar sobre a demora após 60 segundos sem conclusão. Deve preservar a solicitação. Para envios, deve oferecer nova tentativa somente após confirmar a falha, conforme a RN18. Para as demais operações, deve oferecer nova tentativa após o aviso de demora. Verificar também o tratamento de falha do modelo ou das consultas. |
| RNF03 | O sistema deve evitar registros duplicados em novas tentativas da mesma operação, inclusive no recebimento de mensagens, na confirmação pelo chat, na geração de ocorrências agendadas e no cadastro de alocações. O sistema deve acionar no máximo uma tentativa de envio por confirmação, mesmo quando a receber mais de uma vez. |
| RNF04 | Executar cálculos financeiros sobre os registros selecionados e conferir os resultados com valores esperados. A redação pelo modelo deve preservar esses resultados. |
| RNF05 | Proteger consultas e operações internas com validação de tokens JWT, rejeitando acessos sem token válido. Validar a autenticidade dos eventos recebidos por webhook antes de processá-los. |
| RNF06 | Disponibilizar os dados e documentos fornecidos por uma carga reproduzível que preserve originais, identificadores e fontes. Preservar o valor e a descrição originais das quantidades. Usar a unidade explícita no registro mesmo quando o nome da coluna indicar outra. Sinalizar unidades ambíguas e manter essas quantidades fora de somas e conversões até esclarecê-las. Repetir a carga sem duplicar registros nem preencher lacunas com dados fictícios. Na mesma base, a recarga preserva as edições e exclusões feitas no CRUD. Reaproveitar cada mensagem da amostra pelo identificador original. |
| RNF07 | Integrar os canais por adaptadores com uma interface comum. Usar essa interface para conectar novos canais à triagem e, quando houver suporte a envio, ao fluxo de revisão e aprovação. |
| RNF08 | O sistema deve tratar confirmações da mesma versão de um rascunho para o mesmo destinatário e canal como um único envio, inclusive quando ocorrerem em paralelo. O sistema deve seguir a RN18 para novas tentativas desse envio. |
| RNF09 | O sistema deve preservar a versão vigente do registro quando rejeitar uma alteração. |
| RNF10 | O sistema deve preservar análises e esclarecimentos mais recentes quando receber resultados atrasados de tentativas anteriores. |

## Validação da entrega

Definir os resultados esperados antes de testar as 15 mensagens fornecidas e as consultas das três frentes. Conferir extração, classificação, perguntas de esclarecimento, fontes e reconhecimento de informação ausente ou conflitante.

Validar as operações dos CRUDs. Verificar o cadastro de um pedido pelo chat, a geração de uma ocorrência agendada e a consulta de uma alocação no resumo por produtor.

Na aplicação publicada na nuvem, testar em cada canal integrado o recebimento de uma mensagem, a resposta ao remetente e a notificação a um produtor de teste. Conferir a revisão pelo funcionário e o histórico dos envios. Nos canais que usam webhook, verificar que o sistema rejeita eventos que falham na validação de autenticidade.

Com a equipe desconectada, enviar uma mensagem e aguardar uma ocorrência agendada. Ao voltar à aplicação, verificar que a análise da mensagem já está registrada e que a solicitação da ocorrência foi gerada na data prevista.

Executar os fluxos com um funcionário e a base completa. Medir os tempos de análise e consulta e registrar as condições da demonstração. O limite de espera do RNF02 não representa garantia de conclusão nesse prazo.

## Fora do escopo

- Acesso direto de produtores, compradores e auditores à plataforma.
- Alocações automáticas, controle de estoque e reservas, negociação comercial, acompanhamento de entregas e gestão de pagamentos.
