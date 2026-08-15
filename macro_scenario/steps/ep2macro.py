"""Step 2.1 and part of 2.2 - bringing the EP2MACRO output into the case.

Two things come from the converter, and neither is a form variable:

  demand_<period>.csv, demand_LF_<period>.csv, elec_demand_<period>.csv and
  h2_demand_<period>.csv        ->  copied into system/

  CO2_Emissions.csv             ->  system/nodes_<period>.json
      Year,CO2_Total                   CO2 -> co2_source -> max_supply

The demand files arrive with 8760 rows. That is on purpose: the TDR runs at the
end of the pipeline and reduces everything in system/ together, so all series
end up on the same representative periods.

Nothing here is invented: a period the converter did not produce is reported and
the case keeps what it had.
"""

import shutil

from ..csvio import DataError, read_table
from ..jsonio import NodeFile
from ..cards.nodes import node_paths

DEMAND_PATTERNS = ["demand_*.csv", "demand_LF_*.csv", "elec_demand_*.csv", "h2_demand_*.csv"]
EMISSIONS_FILENAME = "CO2_Emissions.csv"
SYSTEM_DIR = "system"
NODE_ID = "co2_source"
SUPPLY_KEY = "max_supply"
YEAR_COLUMNS = ("Year", "year", "Time_Index", "Period")
TOTAL_COLUMNS = ("CO2_Total", "CO2_total", "Total")


def copy_demand_files(case_dir, source_dir, dry_run=False):
    """Copy the demand timeseries into system/. Returns the list of file names."""
    system = case_dir / SYSTEM_DIR
    if not system.is_dir():
        raise DataError(f"{SYSTEM_DIR}/ not found in the case")

    copied = []
    seen = set()
    for pattern in DEMAND_PATTERNS:
        for path in sorted(source_dir.glob(pattern)):
            if path.name in seen:
                continue
            seen.add(path.name)
            if not dry_run:
                shutil.copy2(path, system / path.name)
            copied.append(path.name)

    if not copied:
        raise DataError(f"{source_dir}: no demand file matching {DEMAND_PATTERNS}")
    return copied


def read_emissions(path):
    """{2025: '634911066.2785072', ...} - kept as text, written as given."""
    table = read_table(path)
    year_column = next((c for c in YEAR_COLUMNS if c in table.fieldnames), None)
    total_column = next((c for c in TOTAL_COLUMNS if c in table.fieldnames), None)
    if year_column is None or total_column is None:
        raise DataError(
            f"{path.name}: expected a year column and one of {list(TOTAL_COLUMNS)}, "
            f"found {table.fieldnames}"
        )

    emissions = {}
    for row in table.rows:
        raw_year = (row[year_column] or "").strip()
        raw_total = (row[total_column] or "").strip()
        if not raw_total:
            continue
        try:
            emissions[int(float(raw_year))] = float(raw_total.replace(",", "."))
        except ValueError:
            raise DataError(f"{path.name}: cannot read row '{raw_year}' / '{raw_total}'")
    if not emissions:
        raise DataError(f"{path.name}: no emission values")
    return emissions


def write_emissions(case_dir, emissions, dry_run=False, warn=None):
    """Write CO2_Total into co2_source.max_supply of every period file."""
    changes = []
    for period, path in node_paths(case_dir):
        value = emissions.get(period)
        if value is None:
            if warn:
                warn(f"period {period} is missing from {EMISSIONS_FILENAME}; {path.name} unchanged")
            continue
        nodes = NodeFile(path)
        before, after = nodes.set_list(NODE_ID, SUPPLY_KEY, value)
        if nodes.save(dry_run):
            changes.append({"file": path.name, "period": period, "from": before, "to": after})
    return changes
