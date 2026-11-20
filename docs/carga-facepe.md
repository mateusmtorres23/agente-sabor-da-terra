# Carga da base Facepe

A carga importa o catálogo de produtos, os produtores, os vínculos `ProdutorProduto` e os 20 lotes históricos de `lotes.csv`. Ela é executada por um comando explícito, separado da inicialização da API: reiniciar o serviço **não** executa a carga.

## Pré-requisitos

- Migrações aplicadas: `uv run alembic upgrade head`.
- Arquivos da base presentes em `backend/data/`:
  - `produtores.csv` — cadastro dos 18 produtores.
  - `lotes.csv` — os 20 lotes históricos.

## Execução

```bash
cd backend
uv run python scripts/load_facepe.py
```

Por padrão, o comando lê `backend/data/`. Para outro diretório:

```bash
uv run python scripts/load_facepe.py --data-dir /caminho/para/os/dados
```

A carga é executada uma única vez durante a preparação do ambiente, antes da operação. Produtos e produtores são reaproveitados pelos seus identificadores naturais (nome e código), respeitando as restrições de unicidade do modelo.

## Mapeamento da base para as entidades

### Produtores (`produtores.csv` → `Produtor`)

| Coluna da base | Campo do modelo |
| --- | --- |
| `id` | `code` |
| `nome_completo` | `name` |
| `cpf` | `cpf` |
| `status` (`ativo`/`inativo`) | `active` |
| `telefone` | `phone` |
| `email` | `email` |
| `endereco` | `address` |
| `municipio` | `municipality` |

Colunas de certificação e dados bancários ficam fora desta carga (outras entregas).

### Produtos e vínculos

O catálogo (`Produto`) é formado pelos nomes presentes na coluna `produtos` de `produtores.csv`, separados por vírgula, com espaços removidos e sem duplicatas. Cada produtor é vinculado aos produtos da sua lista em `ProdutorProduto`.

Os nomes já vêm padronizados na base. Em `lotes.csv`, a coluna `produto` pode indicar uma variedade que não é o nome do catálogo — por exemplo, `goiaba paluma` e `manga tommy` correspondem aos produtos `goiaba` e `manga`. O nome original de cada lote é preservado na linha de origem, sem forçar o vínculo ao catálogo.

### Lotes (`lotes.csv` → `Lote`)

| Coluna da base | Uso |
| --- | --- |
| `produtor_id` | resolve para `Produtor.code` → `Lote.producer_id` |
| `quantidade_kg` | `Lote.quantity` (o nome da coluna **não** define a unidade) |
| `data_entrega` | `Lote.delivery_date` |
| `observacao` | fonte da unidade (ver abaixo) |

`Lote.item_id` fica `NULL` e `Lote.availability_confirmed` fica `NULL` (a base não informa a confirmação). As demais colunas do CSV (`lote_id`, `produto`, `pedido_id`, `comprador`, `data_colheita`, `temperatura_transporte_c`, `validade`, `inspecao_visual`, `observacao`, etc.) permanecem nos arquivos de origem e serão disponibilizadas pela indexação documental, sem duplicá-las nas entidades de negócio.

## Tratamento de unidades ambíguas

A unidade vem da observação do registro, nunca do nome da coluna `quantidade_kg`:

- `300 unidades` → unidade `unidades`.
- `150 maços` → unidade `maços`.
- `40 maços (kg)` → **ambígua** (duas unidades distintas) → unidade `NULL`; a quantidade fica fora de somas e conversões até esclarecimento.
- Observações sem unidade (ex.: `Certificação orgânica anexa`) → unidade `NULL`.

Quando a fonte não identifica a unidade, o campo `Lote.unit` permanece vazio e o lote fica fora dos cálculos de saldo e resumo, conforme o RNF06.
