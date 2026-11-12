# Protótipo navegável da Sabor da Terra

## Executar

Abra `index.html` no navegador ou sirva a pasta com um servidor estático.

```bash
python -m http.server 8000 --directory docs/prototype
```

Depois acesse `http://localhost:8000`. A senha de demonstração é `demo`. O navegador simula o agente e os canais com exemplos adaptados do case.

## Roteiro rápido

1. Na **Triagem**, abra `PED-2026-003`, confirme a data de entrega no chat e use **Revisar pedido**. Cadastre o rascunho e abra o pedido. Registre uma alocação de tomate para João da Serra e confira o saldo. O pedido do exemplo `PED-2026-004` permite conferir o bloqueio por falta de comprovação de aptidão.
2. Em **Novo chat**, pergunte por `LOT-2026-0094` para abrir a citação e baixar a fonte. Depois peça um “resumo por produtor” e use **Baixar resumo em PDF**.
3. Abra `PED-2026-009` e use **Revisar resposta** e **Copiar resposta**. Para simular um envio, abra `MSG-TESTE-01` ou registre uma mensagem nova por um canal integrado com um contato de teste. Use **Revisar resposta** e confira o resultado do envio no chat.
4. Em **Agendamentos**, crie uma série semanal. Abra o detalhe e use **Simular triagem** em uma ocorrência pendente. Ela fica disponível na fila de **Triagem**. O calendário da demonstração usa 11/11/2026 como data de referência.
5. Em **Cadastros**, abra um produtor, produto ou documento para consultar e editar seus dados. O detalhe mostra os vínculos que impedem a exclusão. Use **Documento importado sem vínculo** para demonstrar uma exclusão.

Conversas, pedidos, alocações, agendamentos, envios e cadastros ficam no `localStorage`. Para reiniciar a demonstração, remova a chave `sabor-da-terra-prototype-v1` nas ferramentas de desenvolvimento.
