# macro_scenario

Aplica ao case do Macro as escolhas de cenário feitas pelo usuário na plataforma
NetZero Brasil. O Worker busca a configuração no banco, monta o
`scenario_config.csv` (Padroes.md, seção 7) e chama uma única função:

```python
from macro_scenario import apply_scenario_config

report = apply_scenario_config(
    job_id="3f2b...",                    # uuid do job
    scenario_config="scenario_config.csv",
    case_dir="/data/case",               # case já extraído, alterado in-place
    ep2macro_dir="/data/MACRO input",    # opcional
    run_tdr=True,                        # opcional
)
```

O retorno é o AdjustmentReport da seção 5 do Padroes.md, que o Worker publica em
`POST /internal/jobs/{id}/adjustments`.

## Rodando (VS Code ou terminal)

Só precisa de Python 3.8+; o pacote usa apenas a biblioteca padrão, sem instalar
nada. Abra no VS Code a pasta que contém `macro_scenario/` e rode do terminal
integrado — ou pressione F5, que o `.vscode/launch.json` já traz três
configurações prontas. `run_example.py` é o atalho: ajuste as quatro variáveis do
topo e execute.

Pela linha de comando:

```
python -m macro_scenario CASE -c scenario_config.csv --report
python -m macro_scenario CASE -c scenario_config.csv --check      # nada é escrito
python -m macro_scenario CASE --set 25=b --set 24=c               # testar um card
python -m macro_scenario CASE -c config.csv --ep2macro "MACRO input" --tdr
python tests.py
```

Como os cards 27, 28, 29 e 31 podem remover linhas, cada cenário deve começar
com uma cópia nova de `NZB_Default_Scenario`; não reutilize uma pasta que já
recebeu outra combinação de opções.

## Ordem de operação

| etapa | o que roda | onde escreve |
|---|---|---|
| 1 | card 25 — inovação tecnológica | `assets/**/*.csv` (custos) |
| 2.1 | importação EP2MACRO | `system/` (demanda) e `co2_source` nos nós |
| 2.2 | cards 2, 33 e 24 | `system/nodes_*.json` e `system/fuel_prices_*.csv` |
| 3 | cards 27, 28, 29, 30, 31, 32 | `assets/**/*.csv` |
| 4 | TDR | reduz tudo que está em `system/` |

O card 25 vem primeiro porque reescreve os 192 arquivos de assets; qualquer card
que edite os mesmos arquivos precisa vir depois. O TDR vem por último para que
demanda, disponibilidade e preços caiam todos no mesmo Period_map.

## Cards implementados

| id | variável | fonte dos valores | estado |
|---|---|---|---|
| 2 | Net emissions caps | `Emissions_cap_trajectory.csv` (MtCO2e × 1e6) | completo |
| 24 | Fossil fuel wholesale prices | `data/card24_prices.py` | completo (A, B, C) |
| 25 | Energy supply technology innovation | colunas `_25-X` em `assets_full/` | banco só tem B |
| 27 | Hydroelectric power plants | `cards/card27.py` (regra, sem números) | completo |
| 28 | Fossil thermal power plants | `cards/card28.py` (regras + exclusão de candidatas) | completo; 28-C usa `max_capacity = 5000` |
| 29 | Nuclear power plants | `cards/card29.py` (regras + lifetimes + exclusão de candidatas) | flag do limite implementada; valor numérico pendente |
| 30 | Solar and wind power | `data/card30_capacity.py` | só a opção B |
| 31 | Rooftop solar deployment | `cards/card31.py` (regra) | completo |
| 32 | Oil production | `data/card32_emissions.py` | completo |
| 33 | Underground CO2 storage | `data/card33_storage.py` | C e Ceará pendentes |

Os 10 cards do Macro estão implementados. Pendências de dado, não de código:
as opções A e C do card 25 e a opção A do card 30 estão vazias no banco; a opção
C do card 33 e a bacia do Ceará são placeholders. Os cards 28-C e 29-C criam e
ativam `MaxCapacityConstraint`. O card 28-C escreve `max_capacity = 5000` em
todas as usinas a gás mantidas, novas e existentes. O limite numérico do card 29
ainda precisa ser fornecido.

Nos cards 28, 29 e 31, `has_capacity` permanece `TRUE` em todas as linhas que
ficam no cenário. Tecnologias indisponíveis são removidas do CSV de trabalho:
28-B/C removem carvão novo; 28-D também remove gás novo; 29-A/B removem nuclear
nova; e o card 31 mantém somente o bloco de IDs correspondente à opção A, B ou C.
No card 31, a linha mantida recebe `MinCapacityConstraint = FALSE` na opção A e
`TRUE` nas opções B e C. O valor de `min_capacity` não é reescrito: permanece o
valor já cadastrado na própria linha selecionada.

Quando uma linha necessária não estiver em `assets/`, o card 27 a recupera do
`assets_full/`. Na nova estrutura, os campos-base — inclusive `max_capacity` —
são copiados diretamente. O suporte às antigas colunas de custo
`_25-<opção escolhida>` permanece apenas para compatibilidade.

Com a nova estrutura dos arquivos hidrelétricos, o card 27 apenas seleciona
linhas: A mantém novas e existentes nos dois arquivos; B remove somente as
novas de `hydro_res.csv`; C remove as novas de `hydro_res.csv` e
`hydro_ror.csv`. Os valores de `max_capacity`, flags e custos das linhas
mantidas não são alterados.

## Estrutura

```
macro_scenario/
  apply.py              orquestra as etapas e monta o relatório
  scenario_config.py    lê o scenario_config.csv da plataforma
  csvio.py              csv: detecta delimitador, preserva a quebra de linha
  jsonio.py             edita os nodes_*.json sem reformatar o arquivo
  report.py             AdjustmentReport
  cards/
    __init__.py         HANDLERS, STAGE_OF, ORDER  <- registre um card novo aqui
    base.py             o contexto que todo card recebe
    suffix.py           motor das colunas com sufixo (_25-B)
    flags.py            motor dos cards que ligam/desligam colunas por id
    nodes.py            helper dos nodes_<período>.json
    card2.py card24.py card25.py card27.py card28.py
    card29.py card30.py card31.py card32.py card33.py
  data/                 valores de cenário, embutidos no código
  steps/
    ep2macro.py         demanda + CO2_Emissions
    tdr.py              chama o run_tdr.jl
tests.py                testes automatizados sobre um case sintético
```

## Como adicionar um card

1. `cards/card<NN>.py` com uma função `apply(ctx)`.
2. Registre em `cards/__init__.py`: `HANDLERS`, `STAGE_OF` e, se a ordem
   importar, `ORDER`.
3. Os valores vão em `data/card<NN>_*.py`, nunca lidos de planilha em runtime.
4. Um teste em `tests.py`.

Regras que todo card segue (Padroes.md, seção 3): altera o case in-place, é
idempotente, nunca derruba o job por dado ausente, e **nunca escreve vazio por
cima de um valor bom** — valor ausente vira aviso e o case mantém o que tinha.

As gravações são encenadas: `ctx.save()` guarda o arquivo editado em memória e o
orquestrador descarrega tudo quando o handler retorna sem erro. Um card grava
todos os seus arquivos ou nenhum — não existe cenário meio aplicado. Cada arquivo
é escrito num temporário ao lado e movido para o lugar, então uma interrupção não
deixa arquivo truncado.

## Estados no relatório

| status | significado |
|---|---|
| `applied` | valor gravado |
| `unchanged` | o case já estava assim |
| `not_in_database` | opção sem valor definido — o case manteve o dele (aviso) |
| `key_missing` | arquivo ou coluna que o card esperava não existe (aviso) |
| `not_implemented` | variável sem opção marcada no formulário |

Além de `adjustments` (uma entrada por variável do formulário), o relatório traz
`steps`, com o que foi feito fora do formulário — a importação do EP2MACRO e o
TDR.
