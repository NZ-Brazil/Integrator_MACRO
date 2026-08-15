"""Variable 27 - Hydroelectric power plants.

    a  new hydro allowed
    b  no new reservoir hydro
    c  no new hydro at all

Both hydro files hold two blocks of assets: the plants that already exist,
whose id ends in _existing, and the candidates for new capacity, which have no
_existing suffix.  Each row now already carries its correct constraint flags,
costs and physical max_capacity values.

The rule, per file and option:

                    hydro_res                     hydro_ror
    a   all rows, new ones can expand     all rows, new ones can expand
    b   only the _existing rows           all rows, new ones can expand
    c   only the _existing rows           only the _existing rows

"only the _existing rows" means the candidate rows are dropped from the working
file, so no new plant can be built at all.  The card only selects rows: it does
not rewrite can_expand, has_capacity, MaxCapacityConstraint, max_capacity or any
cost.  Every retained row remains exactly as supplied by the asset database.

The row set is rebuilt from assets_full/ every time, which is what makes moving
between options work in both directions: option c drops the candidates, and
going back to a puts them in again. Rows already in the working file are kept as
they are, so whatever an earlier card wrote into them survives; only genuinely
new rows are copied over from the database.

If a candidate row is absent from the working file (for example after applying
B or C), it is restored from assets_full/ when A is selected again. Base fields
present in the new database, including max_capacity, are copied directly. For
compatibility with the legacy database, a missing base cost may still be read
from the corresponding _25-<option> column. Nothing is invented: if neither
source exists, the cell is left empty and the run says so.
"""

from ..csvio import ID_COLUMN, read_table, Table
from .base import CardError
from .suffix import SOURCE_DIR, WORKING_DIR, find_working
from .. import report as R

CARD = "27"
EXISTING_SUFFIX = "_existing"

RES_FILE = "hydro_res.csv"
ROR_FILE = "hydro_ror.csv"

# True keeps every row, False keeps only the ids ending in _existing.
KEEP_CANDIDATES = {
    "A": {RES_FILE: True, ROR_FILE: True},
    "B": {RES_FILE: False, ROR_FILE: True},
    "C": {RES_FILE: False, ROR_FILE: False},
}

COST_CARD = 25  # whose suffixed columns hold the cost of a row added here


def is_existing(asset_id):
    return asset_id.lower().endswith(EXISTING_SUFFIX)


def apply(ctx):
    option = ctx.option
    if option not in KEEP_CANDIDATES:
        raise CardError(
            f"option {option} is not defined for card {CARD}; it has {sorted(KEEP_CANDIDATES)}",
            status=R.NOT_IN_DATABASE,
        )

    source_root = ctx.path(SOURCE_DIR)
    if not source_root.is_dir():
        raise CardError(f"{SOURCE_DIR}/ not found in the case")

    changes = []
    for period_dir in sorted(p for p in source_root.iterdir() if p.is_dir()):
        for filename, keep_candidates in KEEP_CANDIDATES[option].items():
            change = _apply_to_file(ctx, period_dir, filename, keep_candidates)
            if change:
                changes.append(change)

    if not changes:
        ctx.unchanged("assets/**/hydro_*.csv", detail=f"hydro already set for option {option}")
        return

    added = sum(c["added"] for c in changes)
    dropped = sum(c["dropped"] for c in changes)
    cells = sum(c["cells"] for c in changes)
    ctx.applied(
        "assets/**/hydro_*.csv",
        detail=f"{len(changes)} file(s): {added} row(s) added, {dropped} dropped, {cells} cell(s)",
        changes=changes,
    )


def _apply_to_file(ctx, period_dir, filename, keep_candidates):
    source_path = period_dir / filename
    if not source_path.is_file():
        ctx.report.warn(f"[{CARD}] {ctx.relative(source_path)} not found")
        return None

    working_path = find_working(ctx.path(WORKING_DIR, period_dir.name), filename)
    if not working_path.is_file():
        raise CardError(f"{ctx.relative(working_path)} not found, but {filename} is in {SOURCE_DIR}/")

    source = read_table(source_path, key=ID_COLUMN)
    working = read_table(working_path, key=ID_COLUMN)
    cost_option = ctx.chosen(COST_CARD)

    wanted = [row[ID_COLUMN] for row in source.rows
              if keep_candidates or is_existing(row[ID_COLUMN])]
    if not wanted:
        raise CardError(
            f"{ctx.relative(source_path)}: no row left after filtering; is the "
            f"'{EXISTING_SUFFIX}' suffix still in use?",
            status=R.NOT_IN_DATABASE,
        )

    rows = []
    added = []
    empty = set()
    for asset_id in wanted:
        row = working.index.get(asset_id)
        if row is None:
            row, blank = _row_from_source(
                source.index[asset_id], working.fieldnames, source.fieldnames, cost_option)
            if blank:
                empty.update(blank)
            added.append(asset_id)
        rows.append(row)

    dropped = [row[ID_COLUMN] for row in working.rows if row[ID_COLUMN] not in set(wanted)]

    # The new hydro spreadsheets already contain the correct flags and physical
    # limits.  Filtering must not mutate any cell in a retained row.
    cells = 0

    if empty:
        ctx.report.warn(
            f"[{CARD}] {ctx.relative(working_path)}: the row(s) added have no value for "
            f"{', '.join(sorted(empty))}"
            + (f" (card {COST_CARD} option {cost_option} is empty in the database)"
               if cost_option else f" (card {COST_CARD} was not answered in this run)")
        )

    if not added and not dropped and not cells:
        return None

    rebuilt = Table(working_path, working.fieldnames, rows, working.delimiter, working.newline)
    ctx.save(rebuilt)
    return {
        "file": ctx.relative(working_path),
        "added": len(added),
        "dropped": len(dropped),
        "cells": cells,
        "rows": len(rows),
    }


def _row_from_source(source_row, fieldnames, source_fields, cost_option):
    """A working row built from the database row.

    Columns the database has under that exact name are copied. The base cost
    columns are not in the database - they only exist suffixed - so they are
    read from the _<COST_CARD>-<option> column of the same row, which is what
    card 25 would have written. Whatever is still empty is returned so the run
    can report it."""
    row = {}
    blank = set()
    for name in fieldnames:
        value = source_row.get(name)
        if value is None and cost_option:
            for suffix in (f"_{COST_CARD}-{cost_option}", f"_{COST_CARD}{cost_option}"):
                if name + suffix in source_fields:
                    value = source_row.get(name + suffix)
                    break
        if not (value or "").strip() and name not in source_fields:
            blank.add(name)
        row[name] = value or ""
    return row, blank
