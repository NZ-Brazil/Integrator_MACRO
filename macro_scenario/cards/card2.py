"""Variable 2 - Net emissions caps.

The form shows this as a slider, but Macro does not read the slider: the cap
trajectory is computed elsewhere and arrives as a csv,

    Emissions_cap_trajectory.csv
        Year,MACRO_cap_MtCO2e,MAgPIE_cap_MtCO2e
        2025,614,981
        ...
        2050,-100,100

Only the MACRO column is used; the MAgPIE one belongs to another model. Values
are in MtCO2e and the case is in tCO2e, so they are multiplied by 1e6 before
going into

    system/nodes_<period>.json
        CO2 -> co2_emitted_BR -> rhs_policy -> CO2CapConstraint

A period with no row in the csv keeps the cap the case already has, and the run
reports it.
"""

from ..csvio import DataError, read_table
from .base import CardError
from .nodes import open_nodes
from .. import report as R

CARD = "2"
TRAJECTORY_FILENAME = "Emissions_cap_trajectory.csv"
NODE_ID = "co2_emitted_BR"
SECTION = "rhs_policy"
CONSTRAINT = "CO2CapConstraint"
CAP_COLUMN = "MACRO_cap_MtCO2e"
YEAR_COLUMNS = ("Year", "year", "Time_Index", "Period")
MT_TO_T = 1_000_000


def find_trajectory(ctx):
    given = ctx.options.get("emissions_cap")
    if given:
        return ctx.path(given) if not str(given).startswith("/") else given
    for candidate in (ctx.path(TRAJECTORY_FILENAME), ctx.path("system", TRAJECTORY_FILENAME)):
        if candidate.is_file():
            return candidate
    return None


def read_trajectory(path):
    """{2025: 614000000, ...} in tCO2e."""
    table = read_table(path)
    year_column = next((c for c in YEAR_COLUMNS if c in table.fieldnames), None)
    if year_column is None:
        raise CardError(f"{path.name}: no year column; expected one of {list(YEAR_COLUMNS)}")
    if CAP_COLUMN not in table.fieldnames:
        raise CardError(f"{path.name}: no '{CAP_COLUMN}' column")

    caps = {}
    for row in table.rows:
        raw_year = (row[year_column] or "").strip()
        raw_cap = (row[CAP_COLUMN] or "").strip()
        if not raw_cap:
            continue
        try:
            year = int(float(raw_year))
            cap = float(raw_cap.replace(",", "."))
        except ValueError:
            raise CardError(f"{path.name}: cannot read row '{raw_year}' / '{raw_cap}'")
        caps[year] = int(round(cap * MT_TO_T))
    if not caps:
        raise CardError(f"{path.name}: no cap values")
    return caps


def apply(ctx):
    path = find_trajectory(ctx)
    if path is None:
        raise CardError(
            f"{TRAJECTORY_FILENAME} not found in the case; the caps already in the "
            f"node files were kept",
            status=R.NOT_IN_DATABASE,
        )

    caps = read_trajectory(path)
    changes = []

    for period, nodes in open_nodes(ctx):
        cap = caps.get(period)
        if cap is None:
            ctx.report.warn(
                f"[{CARD}] period {period} is missing from {path.name}; "
                f"{nodes.path.name} kept its cap"
            )
            continue
        try:
            before, after = nodes.set(NODE_ID, CONSTRAINT, cap, section=SECTION)
        except DataError as error:
            if ctx.strict:
                raise
            ctx.report.warn(f"[{CARD}] {error}")
            continue
        if nodes.changed:
            ctx.save(nodes)
            changes.append({
                "file": ctx.relative(nodes.path),
                "period": period,
                "from": before,
                "to": after,
            })

    if not changes:
        ctx.unchanged("system/nodes_*.json", detail=f"caps already equal to {path.name}")
        return

    detail = f"{len(changes)} period file(s) from {path.name} (MtCO2e x 1e6)"
    ctx.applied("system/nodes_*.json", detail=detail, changes=changes)
