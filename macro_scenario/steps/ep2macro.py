"""Step 2.1 and part of 2.2 - bringing the EP2MACRO output into the case.

Two things come from the converter, and neither is a form variable:

  demand_<period>.csv, demand_LF_<period>.csv, elec_demand_<period>.csv and
  h2_demand_<period>.csv        ->  copied into system/

  CO2_Emissions.csv             ->  system/nodes_<period>.json
      Year,CO2_Total                   CO2 -> co2_source -> max_supply
                                 ->  assets/assets_<period>/co2_transmission.csv
                                     edges--transmission_edge (Industry_to_Sink)

The emissions total is written into co2_source.max_supply of each
system/nodes_<period>.json, and into the Industry_to_Sink row of every
assets/assets_<period>/co2_transmission.csv.

Industry_to_Sink's existing_capacity is carried between periods by Macro, so it
cannot be used as a period-specific emissions input directly: it is always set
to 0. Instead, four columns are added if not already present -
min_capacity, max_capacity, constraints--MinCapacityConstraint and
constraints--MaxCapacityConstraint - and the emissions total for that period
pins the edge into a [-1, +1] band around itself:

    existing_capacity                        = 0
    min_capacity                             = emissions - 1
    max_capacity                             = emissions + 1
    constraints--MinCapacityConstraint       = TRUE
    constraints--MaxCapacityConstraint       = TRUE

The demand files arrive with 8760 rows. That is on purpose: the TDR runs at the
end of the pipeline and reduces everything in system/ together, so all series
end up on the same representative periods.

Nothing here is invented: a period the converter did not produce is reported and
the case keeps what it had.
"""

import re
import shutil
from pathlib import Path

from ..csvio import DataError, ID_COLUMN, read_table, write_table
from ..jsonio import NodeFile
from ..cards.nodes import node_paths

DEMAND_PATTERNS = ["demand_*.csv", "demand_LF_*.csv", "elec_demand_*.csv", "h2_demand_*.csv"]
EMISSIONS_FILENAME = "CO2_Emissions.csv"
SYSTEM_DIR = "system"
NODE_ID = "co2_source"
SUPPLY_KEY = "max_supply"
YEAR_COLUMNS = ("Year", "year", "Time_Index", "Period")
TOTAL_COLUMNS = ("CO2_Total", "CO2_total", "Total")

# -- Industry_to_Sink / co2_transmission.csv ------------------------------

ASSETS_DIR = "assets"
TRANSMISSION_FILENAME = "co2_transmission.csv"
TRANSMISSION_ASSET_ID = "Industry_to_Sink"
PERIOD_IN_DIRNAME = re.compile(r"(\d{4})$")

EXISTING_CAPACITY = "edges--transmission_edge--existing_capacity"
MIN_CAPACITY = "edges--transmission_edge--min_capacity"
MAX_CAPACITY = "edges--transmission_edge--max_capacity"
MIN_CAPACITY_CONSTRAINT = "edges--transmission_edge--constraints--MinCapacityConstraint"
MAX_CAPACITY_CONSTRAINT = "edges--transmission_edge--constraints--MaxCapacityConstraint"
NEW_COLUMNS = (MIN_CAPACITY, MAX_CAPACITY, MAX_CAPACITY_CONSTRAINT, MIN_CAPACITY_CONSTRAINT)
TRUE = "TRUE"
CAPACITY_BAND = 1


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


def _asset_period_dirs(case_dir):
    """[(2025, Path), (2030, Path), ...] for assets/assets_<period>/."""
    root = Path(case_dir) / ASSETS_DIR
    if not root.is_dir():
        raise DataError(f"{ASSETS_DIR}/ not found in the case")
    found = []
    for path in sorted(p for p in root.iterdir() if p.is_dir()):
        match = PERIOD_IN_DIRNAME.search(path.name)
        if match:
            found.append((int(match.group(1)), path))
    return found


def write_transmission_capacity(case_dir, emissions, dry_run=False, warn=None):
    """Pin the Industry_to_Sink row of every co2_transmission.csv to the CO2_Total
    of its period, as a [-1, +1] band around it rather than a fixed value.

    existing_capacity is carried between periods by Macro, so it always becomes
    0; min_capacity/max_capacity and their constraint flags are added to the
    file when missing and then written for every period.
    """
    changes = []
    for period, folder in _asset_period_dirs(case_dir):
        path = folder / TRANSMISSION_FILENAME
        if not path.is_file():
            if warn:
                warn(f"{path.relative_to(case_dir)} not found")
            continue

        value = emissions.get(period)
        if value is None:
            if warn:
                warn(f"period {period} is missing from {EMISSIONS_FILENAME}; {path.name} unchanged")
            continue

        table = read_table(path, key=ID_COLUMN)
        row = table.index.get(TRANSMISSION_ASSET_ID)
        if row is None:
            if warn:
                warn(f"{path.relative_to(case_dir)}: no '{TRANSMISSION_ASSET_ID}' row")
            continue

        added = False
        for column in NEW_COLUMNS:
            if column not in table.fieldnames:
                table.fieldnames.append(column)
                for other in table.rows:
                    other[column] = other.get(column, "")
                added = True

        cells = 0
        for column, new_value in (
            (EXISTING_CAPACITY, 0),
            (MIN_CAPACITY, value - CAPACITY_BAND),
            (MAX_CAPACITY, value + CAPACITY_BAND),
            (MIN_CAPACITY_CONSTRAINT, TRUE),
            (MAX_CAPACITY_CONSTRAINT, TRUE),
        ):
            if column not in table.fieldnames:
                if warn:
                    warn(f"{path.relative_to(case_dir)}: no '{column}' column")
                continue
            new_value = str(new_value)
            if row[column] != new_value:
                row[column] = new_value
                cells += 1

        if cells or added:
            if not dry_run:
                write_table(table)
            changes.append({"file": str(path.relative_to(case_dir)), "period": period, "cells": cells})
    return changes
