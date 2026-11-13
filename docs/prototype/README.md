# Protótipo navegável da Sabor da Terra

## Executar

Abra `index.html` no navegador ou execute o comando na raiz do repositório.

```bash
python -m http.server 8000 --directory docs/prototype
```

Se usar o servidor estático, acesse `http://localhost:8000`. A senha de demonstração é `demo`. O navegador simula o assistente e os canais com exemplos adaptados da base fornecida.

## Roteiro rápido

1. Na **Triagem**, abra `PED-2026-003` e informe `20/11/2026` no chat. A solicitação passa para **Pronta para decisão**. Use **Revisar pedido** para cadastrar e abrir o pedido, que mostra a solicitação de origem.
2. Abra `PED-2026-004` para ver a pendência de DAP ou CAF e a fonte citada. Use **Revisar pedido** e mantenha o intervalo de `20/11/2026` a `24/11/2026`. No pedido salvo, tente alocar 5 potes de mel ao produtor inativo e confira o bloqueio. Selecione um produtor ativo, marque a confirmação de disponibilidade e salve a alocação. Na **Triagem**, use **Encerrar** e registre o resultado.
3. Em **Novo chat**, pergunte por `LOT-2026-0094` para abrir a citação e baixar a fonte, ou use **Sugerir produtor de tomate** para ver a capacidade estimada. Para testar o resumo financeiro, peça “Gere um resumo de João da Serra com referência em 30/09/2026” e use **Baixar resumo em PDF**.
4. Abra `PED-2026-009` e use **Revisar resposta** e **Copiar resposta**. Nos chats `MSG-TESTE-01` e `MSG-TESTE-02`, use **Revisar resposta** e **Enviar na demonstração**. O primeiro simula um envio confirmado. O segundo mostra **Resultado incerto** no histórico e bloqueia outra tentativa.
5. Em **Agendamentos**, crie uma série semanal com primeiro fornecimento em `17/11/2026` e dois dias de antecedência. Use **Simular triagem** na primeira ocorrência. Depois edite a série e informe `19/11/2026` como primeiro fornecimento. A solicitação de terça-feira é preservada e a primeira entrega de quinta-feira fica para `26/11/2026`. O calendário da demonstração usa 11/11/2026 como data de referência.
6. Em **Cadastros**, abra um produtor, produto ou documento para consultar e editar seus dados. O detalhe mostra os vínculos que impedem a exclusão. Use **Documento importado sem vínculo** para demonstrar uma exclusão.

Conversas, pedidos, alocações, agendamentos, envios e cadastros ficam no `localStorage`. Use uma janela privativa para testar os exemplos atualizados sem mexer nos seus dados. Para reiniciar a demonstração no navegador atual, remova a chave `sabor-da-terra-prototype-v1` nas ferramentas de desenvolvimento.
