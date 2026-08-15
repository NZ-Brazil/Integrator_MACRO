"""Suffixed-column cards.

Several cards are stored the same way: the database keeps one column per option
next to the base column, and applying an option means copying the right column
over the base one.

    assets_full/<period>/<technology>.csv        database
        edges--edge--investment_cost_25-A
        edges--edge--investment_cost_25-B
        edges--edge--investment_cost_25-C
                                    |  option B
                                    v
    assets/<period>/<technology>.csv             working file, read by Macro
        edges--edge--investment_cost

Rows are matched by the 'id' column, not by position. Files in the database
that have no column for the card are left alone. Everything else in the working
file - other columns, other files, row order, column order - is untouched.

Timeseries in system_full/ work the same way. The database file carries the same
name as its target; when the two have the same number of rows the values are
copied row by row, otherwise a constant column is broadcast to every row, which
is what lets an 8760-row database file feed a file reduced by the TDR.

Because the values always come from the database and never from the current
state of the working file, applying a card twice gives the same result, and
applying card 25 then any other card accumulates instead of overwriting.
"""

import re

from ..csvio import DataError, ID_COLUMN, read_table
from .base import CardError
from .. import report as R

SOURCE_DIR = "assets_full"
WORKING_DIR = "assets"
SYSTEM_SOURCE_DIR = "system_full"
SYSTEM_WORKING_DIR = "system"

DECIMAL_COMMA = re.compile(r"^-?\d+,\d+$")


def normalize_stem(stem):
    """beccs_FT3 -> beccs_FT, rooftop_pv_2025 -> rooftop_pv."""
    stem = re.sub(r"_\d{4}$", "", stem)
    return re.sub(r"\d+$", "", stem)


def find_working(working_dir, source_name):
    """Locate the working file for a database file. Names usually match exactly;
    when they do not, fall back to comparing normalized stems."""
    exact = working_dir / source_name
    if exact.is_file():
        return exact

    target = normalize_stem(exact.stem)
    matches = [p for p in sorted(working_dir.glob("*.csv")) if normalize_stem(p.stem) == target]
    if len(matches) > 1:
        raise DataError(
            f"{working_dir}: '{source_name}' matches {[p.name for p in matches]}; "
            f"rename to disambiguate"
        )
    return matches[0] if matches else exact


def scenario_columns(fieldnames, card, option):
    """Map base column name -> suffixed column name, for this card and option."""
    suffix = re.compile(rf"_{re.escape(card)}[-_]?{re.escape(option)}$", re.IGNORECASE)
    return {name[: m.start()]: name for name in fieldnames if (m := suffix.search(name))}


def options_in_file(fieldnames, card):
    pattern = re.compile(rf"_{re.escape(card)}[-_]?([A-Za-z])$")
    return sorted({m.group(1).upper() for name in fieldnames if (m := pattern.search(name))})


def _check_value(value, source, column):
    if DECIMAL_COMMA.match(value or ""):
        raise DataError(
            f"{source}: '{column}' is '{value}'; decimal commas are not valid, use a dot"
        )


def apply_to_assets(ctx, source, working, card, option):
    """Copy the card columns of one database file onto its working file."""
    source_table = read_table(source, key=ID_COLUMN)
    columns = scenario_columns(source_table.fieldnames, card, option)
    if not columns:
        return None, options_in_file(source_table.fieldnames, card)

    if not working.is_file():
        raise CardError(f"{ctx.relative(working)} not found, but {source.name} has columns for card {card}")

    target = read_table(working, key=ID_COLUMN)
    missing = [base for base in columns if base not in target.fieldnames]
    if missing:
        suffixed = [n for n in target.fieldnames if any(n.startswith(b) and n != b for b in missing)]
        hint = f"; found {suffixed} instead" if suffixed else ""
        raise CardError(f"{ctx.relative(working)}: missing column(s) {missing}{hint}")

    absent = [row[ID_COLUMN] for row in target.rows if row[ID_COLUMN] not in source_table.index]
    if absent:
        raise CardError(
            f"{ctx.relative(source)}: missing {len(absent)} row(s) present in the working file: {absent}",
            status=R.NOT_IN_DATABASE,
        )

    changed = 0
    blank = 0
    for row in target.rows:
        source_row = source_table.index[row[ID_COLUMN]]
        for base, suffixed in columns.items():
            value = source_row[suffixed]
            if not (value or "").strip():
                # The option has no value for this cell: keep what the case has.
                # Writing the blank would silently erase a cost.
                blank += 1
                continue
            _check_value(value, ctx.relative(source), suffixed)
            if row[base] != value:
                row[base] = value
                changed += 1

    if changed:
        ctx.save(target)
    return {
        "file": ctx.relative(working),
        "columns": sorted(columns),
        "cells": changed,
        "blank": blank,
    }, None


def apply_to_system(ctx, source, working, card, option):
    """Same idea for the timeseries under system/."""
    source_table = read_table(source)
    columns = scenario_columns(source_table.fieldnames, card, option)
    if not columns:
        return None, options_in_file(source_table.fieldnames, card)

    if not working.is_file():
        raise CardError(f"{ctx.relative(working)} not found, but {source.name} has columns for card {card}")

    target = read_table(working)
    missing = [base for base in columns if base not in target.fieldnames]
    if missing:
        raise CardError(f"{ctx.relative(working)}: missing column(s) {missing}")

    constant = all(len({row[name] for row in source_table.rows}) == 1 for name in columns.values())
    if len(source_table.rows) == len(target.rows):
        values, how = _aligned(source_table, target, source)
    elif constant:
        values = [source_table.rows[0]] * len(target.rows)
        how = f"broadcast from {len(source_table.rows)} row(s)"
    else:
        raise CardError(
            f"{ctx.relative(source)}: has {len(source_table.rows)} rows and {working.name} has "
            f"{len(target.rows)}; the values vary by row, so they cannot be broadcast",
            status=R.NOT_IN_DATABASE,
        )

    changed = 0
    blank = 0
    for row, value_row in zip(target.rows, values):
        for base, suffixed in columns.items():
            value = value_row[suffixed]
            if not (value or "").strip():
                blank += 1
                continue
            _check_value(value, ctx.relative(source), suffixed)
            if row[base] != value:
                row[base] = value
                changed += 1

    if changed:
        ctx.save(target)
    return {
        "file": ctx.relative(working),
        "columns": sorted(columns),
        "cells": changed,
        "blank": blank,
        "how": how,
    }, None


PERIOD_COLUMN = "time_index"


def _period_column(fieldnames):
    return next((name for name in fieldnames if name.casefold() == PERIOD_COLUMN), None)


def _aligned(source_table, target, source):
    """Line the two files up. When both carry a Time_Index, match on it instead
    of trusting the row order - a file re-sorted in Excel would otherwise be
    applied shifted, silently."""
    source_period = _period_column(source_table.fieldnames)
    target_period = _period_column(target.fieldnames)
    if not (source_period and target_period):
        return source_table.rows, "row by row"

    indexed = {}
    for row in source_table.rows:
        key = row[source_period]
        if not key:
            raise CardError(f"{source}: blank '{source_period}'")
        if key in indexed:
            raise CardError(f"{source}: duplicate '{source_period}' {key!r}")
        indexed[key] = row

    absent = [row[target_period] for row in target.rows if row[target_period] not in indexed]
    if absent:
        raise CardError(
            f"{source}: missing {len(absent)} '{source_period}' value(s) present in "
            f"the working file: {absent[:20]}",
            status=R.NOT_IN_DATABASE,
        )
    return [indexed[row[target_period]] for row in target.rows], f"matched by {target_period}"


def apply_card(ctx, card):
    """Run one suffixed-column card over the whole case."""
    option = ctx.option
    source_root = ctx.path(SOURCE_DIR)
    system_root = ctx.path(SYSTEM_SOURCE_DIR)

    if not source_root.is_dir() and not system_root.is_dir():
        raise CardError(f"neither {SOURCE_DIR}/ nor {SYSTEM_SOURCE_DIR}/ found in the case")

    changes = []
    available = set()
    problems = []

    def run(work):
        try:
            change, seen = work()
        except (CardError, DataError) as error:
            if ctx.strict:
                raise
            problems.append(str(error))
            return
        if change is not None:
            changes.append(change)
        available.update(seen or [])

    if source_root.is_dir():
        for period_dir in sorted(p for p in source_root.iterdir() if p.is_dir()):
            working_dir = ctx.path(WORKING_DIR, period_dir.name)
            for source in sorted(period_dir.glob("*.csv")):
                run(lambda s=source, d=working_dir: apply_to_assets(
                    ctx, s, find_working(d, s.name), card, option))

    if system_root.is_dir():
        for source in sorted(system_root.glob("*.csv")):
            working = ctx.path(SYSTEM_WORKING_DIR, source.name)
            run(lambda s=source, w=working: apply_to_system(ctx, s, w, card, option))

    for problem in problems:
        ctx.report.warn(f"[{ctx.answer.variable_id}] {problem}")

    if not changes:
        if available:
            raise CardError(
                f"no column with suffix _{card}-{option} in the database; it has "
                f"option(s) {sorted(available)}",
                status=R.NOT_IN_DATABASE,
            )
        raise CardError(
            f"no column for card {card} in {SOURCE_DIR}/ or {SYSTEM_SOURCE_DIR}/",
            status=R.NOT_IN_DATABASE,
        )

    cells = sum(change["cells"] for change in changes)
    blank = sum(change["blank"] for change in changes)
    filled = sum(1 for change in changes if change["cells"] or change["blank"] == 0)

    if blank and not filled:
        # The columns are there but nobody filled them in. Keeping the case as it
        # is beats writing blanks over real costs, so this is a warning, not a write.
        raise CardError(
            f"the _{card}-{option} columns exist but are empty in {SOURCE_DIR}/ "
            f"({blank} cells in {len(changes)} files); the case kept its current values",
            status=R.NOT_IN_DATABASE,
        )
    if blank:
        ctx.report.warn(
            f"[{ctx.answer.variable_id}] {blank} cell(s) of _{card}-{option} are empty in "
            f"{SOURCE_DIR}/; those kept the value the case already had"
        )

    detail = f"{len(changes)} file(s), {cells} cell(s) from suffix _{card}-{option}"
    touched = [change for change in changes if change["cells"]]
    target = f"{WORKING_DIR}/**/*.csv"
    if cells:
        ctx.applied(target, detail=detail, changes=touched)
    else:
        ctx.unchanged(target, detail=f"{len(changes)} file(s) already at _{card}-{option}")
