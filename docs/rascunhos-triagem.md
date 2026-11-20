# Rascunhos de pedidos na triagem — issue #15

A triagem transforma os dados extraídos em `OrderDraftData`, o contrato de revisão e confirmação da #10. O resultado é um rascunho para revisão; gerar o rascunho não grava um pedido nem confirma itens condicionais.

## Pontos de entrada

`api.agents.triage.prepare_order_draft(analysis, products=...)` transforma uma `TriageAnalysis` já disponível. Use essa função após executar o orquestrador para não chamar o modelo novamente.

`await api.agents.triage.analyze_order_draft(payload, products=..., runner=..., model=...)` executa a triagem existente e retorna o rascunho. `payload` usa o contrato `TriageInput`, incluindo a data original de recebimento. O runner e o modelo são opcionais e seguem a configuração existente dos agentes.

Ambas retornam `OrderDraftData | None`. Consultas, ofertas, comunicados e mensagens não identificadas retornam `None`.

O catálogo é uma sequência de `ProductResponse`, com UUID e nome reais fornecidos pela aplicação. Somente uma correspondência única de nome, normalizando maiúsculas e espaços, preenche `product_id`. Produtos desconhecidos ou com múltiplas correspondências mantêm o identificador vazio e uma pendência. Sem catálogo, os nomes são preservados e todos os vínculos ficam pendentes de confirmação.

## Preservação dos dados

- Comprador, quantidades e unidades são copiados da análise, sem conversões ou preenchimentos presumidos.
- A data única ou o intervalo vem exclusivamente do prazo de entrega. Prazos de resposta ou de documentos não se tornam datas de entrega.
- Datas conflitantes ficam em aberto, com a referência original e a necessidade de confirmação.
- Horário, local, pagamento, frequência, contrato, condições gerais e exigências são preservados em `conditions`.
- Cada item preserva `conditional` e `condition_text`. Exigências de atendimento presentes apenas em `condition_text`, como a certificação orgânica do mel, também entram em `conditions`, identificando o produto, para permanecerem no pedido confirmado pela #10. Expressões de inclusão como “se tiver” ficam no item e não são promovidas a exigências de atendimento. Falta de descrição da condição gera uma pendência.
- Quantidades agregadas ou ambíguas ficam em aberto com a referência original e o esclarecimento necessário. Quantidades incompatíveis com a precisão do contrato também exigem revisão.
- As pendências da análise são mantidas, junto das verificações de exigências e dos dados obrigatórios ausentes.

## Consumo pela aplicação

A integração conversacional pode passar o rascunho a `OrderDraftService.create_draft`, respeitando o titular da conversa ou a solicitação da triagem. A revisão, a retirada de itens condicionais e a confirmação explícita continuam no fluxo da #10. A execução pelos endpoints do chat pertence à #51.

## Validação

Execute em `backend/`:

```sh
uv run pytest tests/unit/agents/test_order_draft.py tests/integration/services/test_triage_order_draft.py
uv run ruff check .
```

Os testes unitários usam o runner simulado da triagem nos caminhos de resposta final e de estado da sessão. Não exigem credenciais nem chamadas ao modelo real. Os testes de integração usam PostgreSQL e verificam o consumo do contrato pela #10 nos chats privado e de triagem.

O cenário compartilhado preserva os dois itens do Mercado Bom Preço, o mel marcado como “se tiver”, a entrega pela manhã e o intervalo de 4 a 8 de novembro de 2026. Na revisão, o mel é retirado, a entrega muda para 6 de novembro e o pedido confirmado contém apenas 10 kg de queijo coalho. Casos adicionais cobrem pendências, catálogo ambíguo, precisão numérica e separação entre prazos de resposta e entrega.

A regressão do `PED-2026-004` usa a mensagem original da Facepe e uma extração simulada focada no mel silvestre. A certificação orgânica aparece somente na condição do item extraído. Após gerar, persistir e confirmar o rascunho, o teste reabre o pedido no PostgreSQL e verifica a preservação dessa exigência, nos fluxos privado e de triagem.
