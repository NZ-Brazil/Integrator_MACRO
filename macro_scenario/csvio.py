"""CSV reading and writing for Macro case files.

The delimiter is detected per file on read (',', ';' or tab), so files re-saved
by Excel in any locale are still readable. Working files are written back comma
separated, which is what Macro expects, and keep the line ending they already
had so a diff shows only the cells that actually changed.

This module is shared by every card handler; the diagnostics here are the ones
that catch the usual damage done by a round trip through Excel.
"""

import csv
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

OUTPUT_DELIMITER = ","
DELIMITERS = [",", ";", "\t"]
ID_COLUMN = "id"


class DataError(ValueError):
    """A case file is missing, malformed or does not carry the requested data."""


def show(delimiter):
    return "tab" if delimiter == "\t" else f"'{delimiter}'"


@dataclass
class Table:
    path: Path
    fieldnames: list
    rows: list
    delimiter: str = OUTPUT_DELIMITER
    newline: str = "\n"
    index: dict = field(default_factory=dict)  # id -> row, when read with a key

    def __len__(self):
        return len(self.rows)


def detect_delimiter(lines, path):
    """Guess the delimiter from the header line and complain about the two
    failure modes Excel produces: trailing empty columns and a header that does
    not use the same separator as the rows."""
    header = lines[0]

    def n_named(delimiter):
        return sum(1 for f in next(csv.reader([header], delimiter=delimiter)) if f.strip())

    delimiter = max(DELIMITERS, key=n_named)
    if n_named(delimiter) < 2:
        raise DataError(f"{path}: could not detect a delimiter in the header")

    if header.rstrip("\r\n").endswith(delimiter):
        raise DataError(
            f"{path}: the header ends with an empty {show(delimiter)} column "
            f"left over from Excel; remove it"
        )

    trailing = {d for d in DELIMITERS if d != delimiter and header.rstrip().endswith(d)}
    if trailing:
        raise DataError(
            f"{path}: the header ends with empty {show(trailing.pop())} columns "
            f"left over from Excel; remove them"
        )

    data = next((line for line in lines[1:] if line.strip()), None)
    if data is not None and data.count(delimiter) == 0:
        other = max(DELIMITERS, key=data.count)
        if data.count(other) > 0:
            raise DataError(
                f"{path}: the header is {show(delimiter)} separated but the rows "
                f"are {show(other)} separated"
            )

    return delimiter


def is_blank(row):
    return all(value in (None, "") for value in row.values() if not isinstance(value, list))


def read_table(path, key=None):
    """Read a csv into a Table. When `key` is given (usually 'id'), every row
    must carry a value for it and the rows are indexed by it."""
    path = Path(path)
    if not path.is_file():
        raise DataError(f"{path} not found")

    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    lines = raw.decode("utf-8-sig").splitlines(keepends=True)
    if not lines:
        raise DataError(f"{path}: empty file")

    delimiter = detect_delimiter(lines, path)
    reader = csv.reader(lines, delimiter=delimiter)
    fieldnames = next(reader)

    blank = [n for n, name in enumerate(fieldnames, start=1) if not name.strip()]
    if blank:
        raise DataError(f"{path}: blank header field(s) at column(s) {blank}")
    repeated = sorted({n for n in fieldnames if fieldnames.count(n) > 1})
    if repeated:
        raise DataError(f"{path}: duplicate header field(s) {repeated}")

    rows = []
    numbers = []
    for values in reader:
        if not values or all(value == "" for value in values):
            continue
        if len(values) != len(fieldnames):
            if len(values) == 1 and delimiter in values[0]:
                detail = "the whole row is in one quoted Excel cell"
            else:
                detail = f"found {len(values)} field(s), expected {len(fieldnames)}"
            raise DataError(f"{path}: line {reader.line_num}: {detail}")
        rows.append(dict(zip(fieldnames, values)))
        numbers.append(reader.line_num)

    table = Table(path, fieldnames, rows, delimiter, newline)
    if key is None:
        return table

    if key not in fieldnames:
        raise DataError(f"{path}: no '{key}' column")

    seen = {}
    for row, number in zip(rows, numbers):
        value = row[key]
        if not value:
            raise DataError(f"{path}: line {number} has no '{key}'")
        if value in seen:
            raise DataError(
                f"{path}: duplicate '{key}' value {value!r} on lines {seen[value]} and {number}"
            )
        seen[value] = number

    table.index = {row[key]: row for row in rows}
    return table


def write_table(table):
    """Write the table back, comma separated, keeping its original line ending.

    Written to a temporary file in the same folder and moved into place, so an
    interrupted run cannot leave a half written case file behind."""
    path = table.path
    mode = path.stat().st_mode if path.exists() else None
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", newline="", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as f:
            temporary = f.name
            writer = csv.DictWriter(
                f,
                fieldnames=table.fieldnames,
                delimiter=OUTPUT_DELIMITER,
                lineterminator=table.newline,
            )
            writer.writeheader()
            writer.writerows(table.rows)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
        temporary = None
    except OSError as error:
        raise DataError(f"{path}: could not be written: {error}") from error
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
