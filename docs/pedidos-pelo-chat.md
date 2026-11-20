# Pedidos pelo chat — issue #10

O rascunho é consultado no chat privado ou na conversa de triagem. A revisão permite corrigir comprador, condições, catálogo, quantidade, unidade e prazo. Apenas itens marcados como condicionais no rascunho persistido podem ser retirados. O cadastro exige confirmação explícita.

## API

| Operação | Chat privado | Triagem |
|---|---|---|
| Consultar rascunho e pedido vinculado | `GET /chat/sessions/{session_id}/order-draft` | `GET /solicitations/{solicitation_id}/order-draft` |
| Confirmar | `POST /chat/sessions/{session_id}/order-drafts/{draft_id}/confirm` | `POST /solicitations/{solicitation_id}/order-drafts/{draft_id}/confirm` |

Todas as rotas exigem JWT. O chat privado exige o proprietário; a triagem é compartilhada entre usuários autenticados. Solicitações finalizadas permitem consulta, mas rejeitam confirmação.

A primeira confirmação retorna 201; uma repetição equivalente retorna 200 com o mesmo pedido. Confirmações distintas na mesma conversa retornam 409 com `detail.code=order_already_confirmed` e `detail.order_id`. Versão desatualizada retorna `order_draft_version_conflict`. Triagem finalizada retorna `solicitation_finished`. Entradas inválidas retornam 422, e conversas ou rascunhos inacessíveis retornam 404.

Pedido, itens e snapshot da confirmação são gravados em uma transação, reutilizando `OrderService.create_order(..., session_id=..., commit=False)`. Bloqueios de linha serializam as confirmações; a restrição única de `orders.session_id` impede duplicação. Cancelar ou editar posteriormente o pedido preserva o vínculo e o snapshot original da confirmação.

## Validação local com rascunhos de teste

Com PostgreSQL disponível e `backend/.env` configurado para o banco local, execute em `backend/`:

```sh
uv run alembic upgrade head
uv run python -m scripts.seed_order_drafts
```

Informe o e-mail de um usuário existente. O script reutiliza ou cadastra os produtos Queijo coalho e Mel e cria duas conversas com rascunhos, sem criar pedidos finais. Reexecutar o mesmo cenário preserva os registros existentes. Para um novo par de conversas, use `--scenario revisao-2`.

1. Abra o chat privado indicado na saída e localize o título `[Teste #10 revisao-1] Mercado Bom Preço`.
2. Confira o comprador, 10 kg de queijo coalho, 5 potes de mel condicional e o período de 04/11/2026 a 08/11/2026.
3. Desmarque o mel, escolha uma única data de entrega em 06/11/2026 e mantenha a condição de entrega pela manhã.
4. Marque a confirmação explícita e confirme. Abra o pedido: deve conter somente 10 kg de queijo coalho e a data revisada.
5. Reabra a conversa: o link deve apontar para o mesmo pedido.
6. Repita o fluxo na triagem pela URL emitida pelo script.
7. Para testar conflito, abra o mesmo rascunho em duas abas antes da confirmação. Confirme dados revisados na primeira; envie dados diferentes na segunda. A segunda deve indicar pedido existente e oferecer seu link, sem criar outro pedido.
8. Cancele o pedido e reabra a conversa: o vínculo deve continuar disponível. Na triagem, finalize a solicitação e confira que o pedido permanece consultável.

A geração automática dos rascunhos pertence à issue #15. O script fornece dados reproduzíveis para validar a revisão e o cadastro desta issue.

## Testes

Backend: `tests/integration/migrations/test_order_draft_migration.py`, `tests/integration/repositories/test_order_draft.py`, `tests/integration/services/test_order_draft.py` e `tests/integration/routers/test_order_draft.py`, além dos testes unitários dos schemas. Os testes do serviço usam conexões independentes para exercitar confirmações simultâneas e verificar rollback real.

Frontend: `tests/orders/orderDraftsApi.test.ts` e `tests/orders/orderDraftPanel.test.tsx`. Execute também `npm run lint`, `npm test` e `npm run build`.
