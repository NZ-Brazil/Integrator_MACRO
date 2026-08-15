"""Variable 30 - Solar and wind power: maximum deployable capacity per asset.

Card 30 no longer decides itself. It is commanded by card 6 (protected
areas): whatever option the platform marks for variable 30 is ignored, and
the option card 6 was answered with picks the outcome instead.

    card 6 A  (No new protected areas from 2024 onwards)
        -> card 30 "A - Less constrained"
    card 6 B  or  card 6 C
        -> card 30 "B - More constrained"

This is also why the scenarios were renamed and swapped position: what used
to be "A - Constrained" is now "B - More constrained", and what used to be
"B - Unconstrained" is now "A - Less constrained".

Card 6 options B and C both land on card 30 option B, but each keeps its own
capacity table - CAPACITY in data/card30_capacity.py has three entries, one
per card 6 option, mapped onto the two card 30 options through
OPTION_OF_DRIVER.

Writes one column, edges--edge--max_capacity, in

    assets/assets_<period>/solar.csv
    assets/assets_<period>/wind_onshore.csv
    assets/assets_<period>/wind_offshore.csv

The same values apply to all six periods. Rows are matched by the asset id, not
by position: the source spreadsheet is ordered like the case today, but that is
not something worth depending on.

An asset present in the table and absent from the case (or the other way round)
is reported, never guessed.
"""

from ..csvio import ID_COLUMN, read_table
from ..data.card30_capacity import CAPACITY, COLUMN, OPTION_OF_DRIVER
from .base import CardError
from .suffix import WORKING_DIR, find_working
from .. import report as R

CARD = "30"
TARGET = "assets/**/{solar,wind_onshore,wind_offshore}.csv"
DRIVER_CARD = 6  # card 30's option comes from this card's answer, not its own


def apply(ctx):
    driver = ctx.chosen(DRIVER_CARD)
    if not driver:
        raise CardError(
            f"card {CARD} is commanded by card {DRIVER_CARD}, which was not answered "
            f"in this run",
            status=R.NOT_IMPLEMENTED,
        )
    if driver not in OPTION_OF_DRIVER:
        raise CardError(
            f"card {DRIVER_CARD} option {driver} is not mapped to a card {CARD} option; "
            f"it has {sorted(OPTION_OF_DRIVER)}",
            status=R.NOT_IN_DATABASE,
        )
    option = OPTION_OF_DRIVER[driver]  # the card 30 option this run resolves to
    origin = f"card {DRIVER_CARD} option {driver}"

    table = CAPACITY.get(driver)
    if not table:
        raise CardError(
            f"{origin} (-> card {CARD} option {option}) has no capacity table yet; "
            f"the case kept its own limits",
            status=R.NOT_IN_DATABASE,
        )

    root = ctx.path(WORKING_DIR)
    if not root.is_dir():
        raise CardError(f"{WORKING_DIR}/ not found in the case")

    changes = []
    for period_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for stem, values in table.items():
            path = find_working(period_dir, f"{stem}.csv")
            if not path.is_file():
                ctx.report.warn(f"[{CARD}] {ctx.relative(period_dir)}/{stem}.csv not found")
                continue

            assets = read_table(path, key=ID_COLUMN)
            if COLUMN not in assets.fieldnames:
                message = f"{ctx.relative(path)}: no '{COLUMN}' column"
                if ctx.strict:
                    raise CardError(message)
                ctx.report.warn(f"[{CARD}] {message}")
                continue

            absent = [i for i in values if i not in assets.index]
            extra = [row[ID_COLUMN] for row in assets.rows if row[ID_COLUMN] not in values]
            if absent or extra:
                ctx.report.warn(
                    f"[{CARD}] {ctx.relative(path)}: {len(absent)} id(s) of the table are not "
                    f"in the file and {len(extra)} id(s) of the file are not in the table"
                )

            changed = 0
            for asset_id, value in values.items():
                row = assets.index.get(asset_id)
                if row is None or value is None:
                    continue
                new = _format(value)
                if row[COLUMN] != new:
                    row[COLUMN] = new
                    changed += 1

            if changed:
                ctx.save(assets)
                changes.append({
                    "file": ctx.relative(path),
                    "columns": [COLUMN],
                    "cells": changed,
                })

    to_label = f"{CARD}-{option}"
    if not changes:
        ctx.unchanged(
            TARGET,
            detail=f"capacities already set for option {option} ({origin})",
        )
        return

    cells = sum(change["cells"] for change in changes)
    ctx.applied(
        TARGET,
        detail=f"{len(changes)} file(s), {cells} cell(s), option {option} ({origin})",
        to=to_label,
        changes=changes,
    )


def _format(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
