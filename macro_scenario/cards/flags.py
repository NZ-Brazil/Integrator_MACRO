"""Cards that switch flags on and off per asset.

Cards 28, 29, 31 and 32 all have the same shape: for every row of a handful of
asset files, look at the id, and write a small set of columns. What changes
between them is which files, which columns, and how the id is read.

A card gives this engine a plan - one rule function per file:

    def rule(asset_id, period) -> {column_name: value} | DROP

and the engine walks assets/assets_<period>/<file>.csv for every period,
applies the rule row by row, and reports one adjustment for the whole card. A
rule that returns nothing for an id leaves that row alone. Returning DROP
removes the row from the working case.

Columns are addressed by name. The scenario spreadsheet writes them as positions
(collum[12], collum[4 and 14]), but a position breaks silently the day a column
is inserted, so the names live in each card module with the index in a comment.
"""

import re

from ..csvio import ID_COLUMN, read_table
from .base import CardError
from .suffix import WORKING_DIR, find_working
from .. import report as R

PERIOD_IN_NAME = re.compile(r"(\d{4})$")
TRUE, FALSE = "TRUE", "FALSE"
DROP = object()


def period_dirs(ctx):
    """[(2025, Path), ...] for the working asset folders."""
    root = ctx.path(WORKING_DIR)
    if not root.is_dir():
        raise CardError(f"{WORKING_DIR}/ not found in the case")
    found = []
    for path in sorted(p for p in root.iterdir() if p.is_dir()):
        match = PERIOD_IN_NAME.search(path.name)
        found.append((int(match.group(1)) if match else None, path))
    if not found:
        raise CardError(f"{WORKING_DIR}/ has no period folder")
    return found


def apply_plan(ctx, card, plan, target, detail=None, new_columns=None):
    """Run one rule per file over every period.

    ``plan`` is ``{filename: rule}``. ``new_columns`` optionally maps a
    filename to columns that the card is explicitly allowed to add, together
    with their default values. This is used when a scenario activates a Macro
    constraint whose flag is not present in the default CSV schema.
    """
    changes = []
    missing_columns = set()
    new_columns = new_columns or {}

    for period, folder in period_dirs(ctx):
        for filename, rule in plan.items():
            path = find_working(folder, filename)
            if not path.is_file():
                ctx.report.warn(f"[{card}] {ctx.relative(folder)}/{filename} not found")
                continue

            table = read_table(path, key=ID_COLUMN)
            cells = 0
            for column, default in new_columns.get(filename, {}).items():
                if column in table.fieldnames:
                    continue
                table.fieldnames.append(column)
                for row in table.rows:
                    row[column] = str(default)
                    cells += 1

            dropped_ids = set()
            for row in table.rows:
                decision = rule(row[ID_COLUMN], period)
                if decision is DROP:
                    dropped_ids.add(id(row))
                    continue
                for column, value in (decision or {}).items():
                    if column not in table.fieldnames:
                        missing_columns.add(f"{filename}:{column}")
                        continue
                    value = str(value)
                    if row[column] != value:
                        row[column] = value
                        cells += 1

            rows = len(dropped_ids)
            if rows:
                table.rows = [row for row in table.rows if id(row) not in dropped_ids]

            if cells or rows:
                ctx.save(table)
                changes.append({
                    "file": ctx.relative(path),
                    "cells": cells,
                    "rows_removed": rows,
                    "period": period,
                })

    if missing_columns:
        message = f"missing column(s): {', '.join(sorted(missing_columns))}"
        if ctx.strict:
            raise CardError(message)
        ctx.report.warn(f"[{card}] {message}")

    if not changes:
        ctx.unchanged(target, detail=f"already set for option {ctx.option}")
        return

    cells = sum(change["cells"] for change in changes)
    rows = sum(change["rows_removed"] for change in changes)
    parts = [f"{len(changes)} file(s)", f"{cells} cell(s)"]
    if rows:
        parts.append(f"{rows} row(s) removed")
    ctx.applied(
        target,
        detail=detail or ", ".join(parts),
        changes=changes,
    )


def check_option(ctx, card, options):
    if ctx.option not in options:
        raise CardError(
            f"option {ctx.option} is not defined for card {card}; it has {sorted(options)}",
            status=R.NOT_IN_DATABASE,
        )
