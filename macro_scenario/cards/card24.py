"""Variable 24 - Fossil fuel wholesale prices.

    a Lower / b Middle range / c Higher

The trajectories are in data/card24_prices.py - one value per fuel and period,
in the code, not read from a spreadsheet at run time.

Prices in Macro are hourly series, so the value of a period is written into
every row of

    system/fuel_prices_<period>.csv

How many rows that is depends on whether the TDR has run: 8760 in a full case,
2016 in a reduced one. Either way every row gets the period's value, so the card
works on both.

Two things are deliberately conservative: a fuel with no value yet (None) keeps
the price the case already has, and a fuel that this case does not price at all
is reported in notes instead of being invented.
"""

import re

from ..csvio import read_table
from ..data.card24_prices import PRICES
from .base import CardError
from .. import report as R

CARD = "24"
TARGET_DIR = "system"
TARGET_PATTERN = "fuel_prices_*.csv"
PERIOD_IN_NAME = re.compile(r"fuel_prices_(\d{4})", re.IGNORECASE)


def apply(ctx):
    option = ctx.option
    if option not in PRICES:
        raise CardError(
            f"option {option} is not defined for card {CARD}; it has {sorted(PRICES)}",
            status=R.NOT_IN_DATABASE,
        )

    trajectory = PRICES[option]
    targets = sorted(ctx.path(TARGET_DIR).glob(TARGET_PATTERN))
    if not targets:
        raise CardError(f"no {TARGET_DIR}/{TARGET_PATTERN} in the case")

    changes = []
    unpriced = set()
    pending = set()

    for path in targets:
        match = PERIOD_IN_NAME.search(path.name)
        if not match:
            continue
        period = int(match.group(1))
        prices = trajectory.get(period)
        if prices is None:
            message = f"period {period} has no prices for option {option}; {path.name} unchanged"
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
            ctx.report.warn(f"[{CARD}] {path.name}: no fuel of option {option} matches this file")
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
                "file": ctx.relative(path),
                "columns": columns,
                "cells": changed,
                "period": period,
            })

    if pending:
        ctx.report.warn(
            f"[{CARD}] option {option}: no price yet for {', '.join(sorted(pending))}; "
            f"the case kept its own"
        )
    if unpriced:
        ctx.note(f"[{CARD}] not priced by Macro in this case, skipped: {', '.join(sorted(unpriced))}")

    target = f"{TARGET_DIR}/{TARGET_PATTERN}"
    if not changes:
        ctx.unchanged(target, detail=f"prices already at option {option}")
        return

    cells = sum(change["cells"] for change in changes)
    ctx.applied(target, detail=f"{len(changes)} period file(s), {cells} cell(s)", changes=changes)


def _format(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return repr(value) if isinstance(value, float) else str(value)
