"""Step 2.1 and part of 2.2 - bringing the EP2MACRO output into the case.

Three things come from the converter (or from the files it produces), and
none of them is a form variable:

  demand_<period>.csv, demand_LF_<period>.csv, elec_demand_<period>.csv and
  h2_demand_<period>.csv        ->  copied into system/

  CO2_Emissions.csv             ->  system/nodes_<period>.json
      Year,CO2_Total                   CO2 -> co2_source -> max_supply
                                 ->  assets/assets_<period>/co2_transmission.csv
                                     edges--transmission_edge (Industry_to_Sink)

  system/demand_LF_<period>.csv ->  system/nodes_<period>.json
      (just copied above, read again here)   rhs_policy -> AggregatedDemandConstraint
                                              on every node in DEMAND_NODE_COLUMN

The emissions total is written into co2_source.max_supply of each
system/nodes_<period>.json, and into the Industry_to_Sink row of every
assets/assets_<period>/co2_transmission.csv.

The AggregatedDemandConstraint on the liquid-fuel demand nodes (gasoline,
ethanol, flexfuel, both jet fuel mandates, biodiesel mandate, diesel) ships in
the case as a placeholder unrelated to any real demand - see
write_demand_constraints() below. This step recomputes it from the same
demand_LF_<period>.csv that was just copied into system/, so it must run
before any card that reads these nodes (card 23 reads them to size the
fossil-fuel supply ceiling; a placeholder there means card 23 sizes that
ceiling against a fictitious demand).

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

import json
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


# -- AggregatedDemandConstraint on the liquid-fuel demand nodes -----------

# node id -> its column in system/demand_LF_<period>.csv. Every one of these
# nodes ships with a placeholder AggregatedDemandConstraint in the case
# template (e.g. gasoline_demand_BR ships with 76 877 727 - about 2.1x what
# the 2025 demand file actually implies; ethanol_demand_BR is off by 3.9x the
# other way). This step replaces the placeholder with the real annual figure,
# period by period.
DEMAND_NODE_COLUMN = {
    "ethanol_demand_BR": "Demand_Ethanol",
    "gasoline_demand_BR": "Demand_Gasoline",
    "flexfuel_demand_BR": "Demand_Flexfuel",
    "jetfuel_flex_demand_BR": "Demand_Jetfuel",
    "jetfuel_SAF_mandate_demand_BR": "Demand_SAF_Jetfuel",
    "jetfuel_fossil_mandate_demand_BR": "Demand_fossil_Jetfuel",
    "biodiesel_mandate_demand_BR": "Demand_BioDiesel",
    "diesel_demand_BR": "Demand_Diesel",
}

DEMAND_LF_FILENAME = "demand_LF_{period}.csv"
AGG_DEMAND_KEY = "AggregatedDemandConstraint"

# Same quirk card 23 already works around: the case writes this section as
# CMOUT_rhs_policy on the gasoline/ethanol/flexfuel/diesel-family nodes and
# CMout_rhs_policy on the jet fuel mandate ones. Try both, then the plain
# rhs_policy as a last resort.
AGG_DEMAND_SECTIONS = ("CMOUT_rhs_policy", "CMout_rhs_policy", "rhs_policy")

TIME_DATA_FILENAME = "time_data.json"
COMMODITY = "LiquidFuels"
DEFAULT_HOURS = 8760
DEFAULT_HOURS_PER_STEP = 1

# How far apart two rows of a supposedly flat column may be (relative to the
# larger of the two) before it is reported as not actually flat.
FLAT_TOLERANCE = 1e-6


def _annual_steps(case_dir, warn=None):
    """TotalHoursModeled / HoursPerTimeStep[LiquidFuels] - how many times a
    flat per-time-step demand value stands for a whole year (8760 in this
    case). This does NOT come from counting rows in demand_LF_<period>.csv:
    that file may already be TDR-reduced (fewer, weighted rows) by the time
    this runs on an existing case, and counting rows would then undercount
    the year by whatever factor TDR reduced it. Mirrors the same read in
    cards/card23.py (steps_per_year); duplicated rather than imported because
    steps/ only depends on cards/ for node_paths, not for card logic."""
    path = case_dir / SYSTEM_DIR / TIME_DATA_FILENAME
    if not path.is_file():
        if warn:
            warn(f"{SYSTEM_DIR}/{TIME_DATA_FILENAME} not found; assuming {DEFAULT_HOURS} time step(s) per year")
        return DEFAULT_HOURS
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    total = data.get("TotalHoursModeled", DEFAULT_HOURS)
    per_step = data.get("HoursPerTimeStep", {})
    if isinstance(per_step, dict):
        per_step = per_step.get(COMMODITY, DEFAULT_HOURS_PER_STEP)
    per_step = per_step or DEFAULT_HOURS_PER_STEP
    steps = total / per_step
    if steps <= 0:
        raise DataError(
            f"{SYSTEM_DIR}/{TIME_DATA_FILENAME}: TotalHoursModeled {total} and "
            f"HoursPerTimeStep {per_step} give no time step per year"
        )
    return steps


def _flat_value(table, column, warn=None):
    """The column's value, checked - not just assumed - to be the same in
    every row. Every fuel in demand_LF_<period>.csv except none (electricity
    and hydrogen live in separate files) is flat across the year; if a column
    turns out not to be flat this reports it and still proceeds on the first
    row, rather than silently averaging or summing rows of unequal weight."""
    values = [float(row[column]) for row in table.rows if (row.get(column) or "").strip() != ""]
    if not values:
        raise DataError(f"{table.path.name}: column '{column}' has no values")
    lo, hi = min(values), max(values)
    if hi - lo > FLAT_TOLERANCE * max(1.0, abs(hi)) and warn:
        warn(
            f"{table.path.name}: '{column}' is not flat (min {lo:,.3f}, max {hi:,.3f}); "
            f"using its first row anyway"
        )
    return values[0]


def write_demand_constraints(case_dir, dry_run=False, warn=None):
    """Replace the AggregatedDemandConstraint placeholder on every node in
    DEMAND_NODE_COLUMN with the annual demand implied by that period's
    system/demand_LF_<period>.csv: the mapped column's flat value x the
    number of time steps in a year (_annual_steps, 8760 in this case).

    Must run after copy_demand_files() (needs demand_LF_<period>.csv already
    in system/) and before the system-stage cards - card 23 in particular
    reads these same nodes to size the fossil-fuel supply ceiling, so it must
    see the real figure, not the template's placeholder.
    """
    case_dir = Path(case_dir)
    steps = _annual_steps(case_dir, warn=warn)
    changes = []

    for period, path in node_paths(case_dir):
        demand_path = case_dir / SYSTEM_DIR / DEMAND_LF_FILENAME.format(period=period)
        if not demand_path.is_file():
            if warn:
                warn(f"{demand_path.relative_to(case_dir)} not found; {path.name} kept its {AGG_DEMAND_KEY}")
            continue

        table = read_table(demand_path)
        nodes = NodeFile(path)
        edited = []

        for node_id, column in DEMAND_NODE_COLUMN.items():
            if column not in table.fieldnames:
                if warn:
                    warn(f"{demand_path.name}: no '{column}' column for node '{node_id}'")
                continue
            value = round(_flat_value(table, column, warn=warn) * steps)

            for section in AGG_DEMAND_SECTIONS:
                try:
                    before, after = nodes.set(node_id, AGG_DEMAND_KEY, value, section=section)
                except DataError:
                    continue
                if before != after:
                    edited.append(node_id)
                break
            else:
                if warn:
                    warn(
                        f"{path.name}: node '{node_id}' has no {AGG_DEMAND_KEY} in any of "
                        f"{', '.join(AGG_DEMAND_SECTIONS)}"
                    )

        if nodes.save(dry_run):
            changes.append({"file": path.name, "period": period, "nodes": edited})

    return changes
