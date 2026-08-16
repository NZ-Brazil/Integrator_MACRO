"""Variable 24 - Fossil fuel wholesale prices, by option and period.

    a Lower / b Middle range / c Higher

The trajectories are in data/card24_prices.py - one value per fuel and period,
in the code, not read from a spreadsheet at run time.

Prices in Macro reach the case two ways, and this card writes both:

  - Hourly series. The value of a period is written into every row of

        system/fuel_prices_<period>.csv

    How many rows that is depends on whether the TDR has run: 8760 in a full
    case, 2016 in a reduced one. Either way every row gets the period's
    value, so the card works on both. natgas, coal, coal_imported and
    uranium read their price only this way, through a "price"/"timeseries"
    reference in the node file.

  - Literal supply price. gasoline_fossil_BR, jetfuel_fossil_BR and
    diesel_fossil_BR additionally carry their own price as a single number
    in every

        system/nodes_<period>.json

    e.g. "price_supply": [ 46.2276014654135 ]. The card writes the same
    period value there too, so the case is correct whichever of the two a
    given node file actually reads.

Two things are deliberately conservative: a fuel with no value yet (None)
keeps the price the case already has, and a fuel that this case does not
price at all is reported in notes instead of being invented.
"""

import re

from ..csvio import DataError, read_table
from ..data.card24_prices import PRICES
from .base import CardError
from .nodes import open_nodes
from .. import report as R

CARD = "24"
TARGET_DIR = "system"
TARGET_PATTERN = "fuel_prices_*.csv"
PERIOD_IN_NAME = re.compile(r"fuel_prices_(\d{4})", re.IGNORECASE)

NODES_TARGET = "system/nodes_*.json"
PRICE_SUPPLY_KEY = "price_supply"

# fuel, as named in data/card24_prices.py -> node id that also carries its
# own "price_supply" in system/nodes_<period>.json, on top of the csv.
NODE_IDS = {
    "gasoline_fossil_price_BR": "gasoline_fossil_BR",
    "diesel_fossil_price_BR": "diesel_fossil_BR",
    "jetfuel_fossil_price_BR": "jetfuel_fossil_BR",
}


def apply(ctx):
    option = ctx.option
    if option not in PRICES:
        raise CardError(
            f"option {option} is not defined for card {CARD}; it has {sorted(PRICES)}",
            status=R.NOT_IN_DATABASE,
        )

    trajectory = PRICES[option]
    unpriced = set()
    pending = set()

    changes = _apply_fuel_prices(ctx, trajectory, unpriced, pending)
    changes += _apply_node_prices(ctx, trajectory, pending)

    if pending:
        ctx.report.warn(
            f"[{CARD}] option {option}: no price yet for {', '.join(sorted(pending))}; "
            f"the case kept its own"
        )
    if unpriced:
        ctx.note(f"[{CARD}] not priced by Macro in this case, skipped: {', '.join(sorted(unpriced))}")

    target = f"{TARGET_DIR}/{TARGET_PATTERN}, {NODES_TARGET}"
    if not changes:
        ctx.unchanged(target, detail=f"prices already at option {option}")
        return

    csv_files = sum(1 for c in changes if c["kind"] == "csv")
    node_files = sum(1 for c in changes if c["kind"] == "node")
    cells = sum(c["cells"] for c in changes)
    ctx.applied(
        target,
        detail=f"{csv_files} fuel_prices file(s), {node_files} nodes file(s), {cells} cell(s)",
        changes=changes,
    )


def _apply_fuel_prices(ctx, trajectory, unpriced, pending):
    targets = sorted(ctx.path(TARGET_DIR).glob(TARGET_PATTERN))
    if not targets:
        raise CardError(f"no {TARGET_DIR}/{TARGET_PATTERN} in the case")

    changes = []
    for path in targets:
        match = PERIOD_IN_NAME.search(path.name)
        if not match:
            continue
        period = int(match.group(1))
        prices = trajectory.get(period)
        if prices is None:
            message = f"period {period} has no prices for option {ctx.option}; {path.name} unchanged"
            if ctx.strict:
                raise CardError(message, status=R.NOT_IN_DATABASE)
            ctx.report.warn(f"[{CARD}] {message}")
            continue

        table = read_table(path)
        unpriced.update(f for f in prices if f not in table.fieldnames)
        columns = []
        for fuel in table.fieldnames:
            if fuel not in prices:
                continue
            if prices[fuel] is None:
                pending.add(fuel)
                continue
            columns.append(fuel)

        if not columns:
            ctx.report.warn(f"[{CARD}] {path.name}: no fuel of option {ctx.option} matches this file")
            continue

        changed = 0
        for row in table.rows:
            for fuel in columns:
                value = _format(prices[fuel])
                if row[fuel] != value:
                    row[fuel] = value
                    changed += 1

        if changed:
            ctx.save(table)
            changes.append({
                "kind": "csv",
                "file": ctx.relative(path),
                "columns": columns,
                "cells": changed,
                "period": period,
            })
    return changes


def _apply_node_prices(ctx, trajectory, pending):
    changes = []
    for period, nodes in open_nodes(ctx):
        prices = trajectory.get(period)
        if prices is None:
            continue  # already reported by _apply_fuel_prices for this period

        edited = []
        for fuel, node_id in NODE_IDS.items():
            if fuel not in prices:
                continue
            value = prices[fuel]
            if value is None:
                pending.add(fuel)
                continue
            try:
                before, after = nodes.set_list(node_id, PRICE_SUPPLY_KEY, value)
            except DataError as error:
                if ctx.strict:
                    raise
                ctx.report.warn(f"[{CARD}] {error}")
                continue
            if before != after:
                edited.append(node_id)

        if nodes.changed:
            ctx.save(nodes)
            changes.append({
                "kind": "node",
                "file": ctx.relative(nodes.path),
                "nodes": edited,
                "cells": len(edited),
                "period": period,
            })
    return changes


def _format(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return repr(value) if isinstance(value, float) else str(value)
