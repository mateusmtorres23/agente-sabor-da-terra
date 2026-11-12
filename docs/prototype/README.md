# Protótipo navegável da Sabor da Terra

## Executar

Abra `index.html` no navegador ou execute o comando na raiz do repositório.

```bash
python -m http.server 8000 --directory docs/prototype
```

Se usar o servidor estático, acesse `http://localhost:8000`. A senha de demonstração é `demo`. O navegador simula o assistente e os canais com exemplos adaptados da base fornecida.

## Roteiro rápido

1. Na **Triagem**, abra `PED-2026-003`, informe uma nova data de entrega no chat, como `20/11/2026`, e use **Revisar pedido**. Cadastre e abra o pedido. Registre uma alocação de tomate para João da Serra, marque a confirmação de disponibilidade e confira o saldo. Para ver o bloqueio por falta de comprovação da vigência do DAP/CAF, cadastre o pedido de `PED-2026-004` pelo chat e tente alocar o item de mel.
2. Em **Novo chat**, pergunte por `LOT-2026-0094` para abrir a citação e baixar a fonte. Depois peça um “resumo por produtor” e use **Baixar resumo em PDF**.
3. Abra `PED-2026-009` e use **Revisar resposta** e **Copiar resposta**. Para simular um envio, abra `MSG-TESTE-01`. Também é possível usar **Registrar mensagem** na triagem e preencher o canal e o contato de teste. No chat da solicitação, use **Revisar resposta**, selecione **Enviar na demonstração** e confira o resultado.
4. Em **Agendamentos**, crie uma série semanal com primeiro fornecimento em `20/11/2026` e dois dias de antecedência. Abra o detalhe e use **Simular triagem** na primeira ocorrência pendente. A solicitação aparece na fila de **Triagem**. O calendário da demonstração usa 11/11/2026 como data de referência.
5. Em **Cadastros**, abra um produtor, produto ou documento para consultar e editar seus dados. O detalhe mostra os vínculos que impedem a exclusão. Use **Documento importado sem vínculo** para demonstrar uma exclusão.

Conversas, pedidos, alocações, agendamentos, envios e cadastros ficam no `localStorage`. Para reiniciar a demonstração, remova a chave `sabor-da-terra-prototype-v1` nas ferramentas de desenvolvimento.
