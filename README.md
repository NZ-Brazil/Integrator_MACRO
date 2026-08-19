# macro_scenario

Applies the scenario choices the user made on the NetZero Brazil platform to the
Macro case. The Worker fetches the configuration from the database, builds the
`scenario_config.csv` (Padroes.md, section 7), and calls a single function:

```python
from macro_scenario import apply_scenario_config

report = apply_scenario_config(
    job_id="3f2b...",                    # job uuid
    scenario_config="scenario_config.csv",
    case_dir="/data/case",               # already-extracted case, modified in-place
    ep2macro_dir="/data/MACRO input",    # optional
    run_tdr=True,                        # optional
)
```

The return value is the AdjustmentReport from section 5 of Padroes.md, which the
Worker publishes to `POST /internal/jobs/{id}/adjustments`.

## Running (VS Code or terminal)

Only needs Python 3.8+; the package uses only the standard library, nothing to
install. Open the folder containing `macro_scenario/` in VS Code and run it from
the integrated terminal — or press F5, since `.vscode/launch.json` already
ships three ready-made configurations. `run_example.py` is the shortcut: adjust
the four variables at the top and run it.

From the command line:

```
python -m macro_scenario CASE -c scenario_config.csv --report
python -m macro_scenario CASE -c scenario_config.csv --check      # nothing is written
python -m macro_scenario CASE --set 25=b --set 24=c               # test a single card
python -m macro_scenario CASE -c config.csv --ep2macro "MACRO input" --tdr
python tests.py
```

Since cards 27, 28, 29 and 31 can remove rows, each scenario must start from a
fresh copy of `NZB_Default_Scenario`; don't reuse a folder that has already
received a different combination of options.

## Order of operations

| step | what runs | where it writes |
|---|---|---|
| 1 | card 25 — technological innovation | `assets/**/*.csv` (costs) |
| 2.1 | EP2MACRO import | `system/` (demand) and `co2_source` on the nodes |
| 2.2 | cards 2, 33 and 24 | `system/nodes_*.json` and `system/fuel_prices_*.csv` |
| 3 | cards 27, 28, 29, 30, 31, 32 | `assets/**/*.csv` |
| 4 | TDR | reduces everything under `system/` |

Card 25 runs first because it rewrites the 192 asset files; any card that edits
the same files needs to come after it. TDR runs last so that demand,
availability and prices all fall onto the same Period_map.

## Implemented cards

| id | variable | source of values | status |
|---|---|---|---|
| 2 | Net emissions caps | `Emissions_cap_trajectory.csv` (MtCO2e × 1e6) | complete |
| 24 | Fossil fuel wholesale prices | `data/card24_prices.py` | complete (A, B, C) |
| 25 | Energy supply technology innovation | `_25-X` columns in `assets_full/` | database only has B |
| 27 | Hydroelectric power plants | `cards/card27.py` (rule, no numbers) | complete |
| 28 | Fossil thermal power plants | `cards/card28.py` (rules + candidate exclusion) | complete; 28-C uses `max_capacity = 5000` |
| 29 | Nuclear power plants | `cards/card29.py` (rules + lifetimes + candidate exclusion) | limit flag implemented; numeric value pending |
| 30 | Solar and wind power | `data/card30_capacity.py` | only option B |
| 31 | Rooftop solar deployment | `cards/card31.py` (rule) | complete |
| 32 | Oil production | `data/card32_emissions.py` | complete |
| 33 | Underground CO2 storage | `data/card33_storage.py` | C and Ceará pending |

All 10 Macro cards are implemented. What remains is missing data, not missing
code: options A and C of card 25 and option A of card 30 are empty in the
database; option C of card 33 and the Ceará basin are placeholders. Cards 28-C
and 29-C create and activate `MaxCapacityConstraint`. Card 28-C writes
`max_capacity = 5000` on every gas plant kept, whether new or existing. The
numeric limit for card 29 still needs to be supplied.

In cards 28, 29 and 31, `has_capacity` stays `TRUE` on every row that remains
in the scenario. Unavailable technologies are removed from the working CSV:
28-B/C remove new coal; 28-D also removes new gas; 29-A/B remove new nuclear;
and card 31 keeps only the block of IDs corresponding to option A, B or C. In
card 31, the row that's kept gets `MinCapacityConstraint = FALSE` under option
A and `TRUE` under options B and C. The `min_capacity` value itself is not
rewritten: it stays whatever was already registered on the selected row.

When a required row is missing from `assets/`, card 27 retrieves it from
`assets_full/`. With the new structure, the base fields — including
`max_capacity` — are copied directly. Support for the old `_25-<chosen option>`
cost columns remains only for backward compatibility.

With the new structure of the hydroelectric files, card 27 only selects rows:
A keeps both new and existing plants in both files; B removes only the new
ones from `hydro_res.csv`; C removes the new ones from both `hydro_res.csv`
and `hydro_ror.csv`. The `max_capacity` values, flags and costs of the rows
that are kept are left unchanged.

## Structure

```
macro_scenario/
  apply.py              orchestrates the steps and builds the report
  scenario_config.py    reads the platform's scenario_config.csv
  csvio.py              csv: detects the delimiter, preserves the line ending
  jsonio.py             edits the nodes_*.json files without reformatting them
  report.py             AdjustmentReport
  cards/
    __init__.py         HANDLERS, STAGE_OF, ORDER  <- register a new card here
    base.py             the context every card receives
    suffix.py           engine for suffixed columns (_25-B)
    flags.py             engine for cards that toggle columns on/off by id
    nodes.py             helper for nodes_<period>.json
    card2.py card24.py card25.py card27.py card28.py
    card29.py card30.py card31.py card32.py card33.py
  data/                 scenario values, embedded in the code
  steps/
    ep2macro.py         demand + CO2_Emissions
    tdr.py               calls run_tdr.jl
tests.py                automated tests against a synthetic case
```

## How to add a card

1. `cards/card<NN>.py` with an `apply(ctx)` function.
2. Register it in `cards/__init__.py`: `HANDLERS`, `STAGE_OF` and, if order
   matters, `ORDER`.
3. Values go in `data/card<NN>_*.py`, never read from a spreadsheet at runtime.
4. A test in `tests.py`.

Rules every card follows (Padroes.md, section 3): it modifies the case
in-place, is idempotent, never fails the job over missing data, and **never
writes an empty value over a good one** — a missing value becomes a warning
and the case keeps what it already had.

Writes are staged: `ctx.save()` keeps the edited file in memory, and the
orchestrator flushes everything once the handler returns without error. A
card writes all of its files or none — there is no such thing as a
half-applied scenario. Each file is written to a temp file alongside it and
then moved into place, so an interruption never leaves a truncated file.

## Report statuses

| status | meaning |
|---|---|
| `applied` | value written |
| `unchanged` | the case was already like this |
| `not_in_database` | option has no defined value — the case kept its own (warning) |
| `key_missing` | a file or column the card expected doesn't exist (warning) |
| `not_implemented` | variable with no option selected on the form |

Besides `adjustments` (one entry per form variable), the report includes
`steps`, covering what was done outside the form — the EP2MACRO import and
the TDR.
