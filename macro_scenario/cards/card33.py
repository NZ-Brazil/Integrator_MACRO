"""Variable 33 - Underground CO2 storage.

    a  storage not allowed          -> CO2StorageConstraint turned off
    b  storage allowed              -> the annual injection allowance per basin
    c  higher annual potential      -> same shape, values still to be defined

Target, in every period file:

    system/nodes_<period>.json
        CO2Captured -> co2_storage_<basin> -> constraints  -> CO2StorageConstraint
                                           -> rhs_policy   -> CO2StorageConstraint

Option a switches the constraint off rather than writing a zero, which is what
"not allowed" means in Macro. Switching back to b turns it on again, so moving
between options is symmetric.

A basin whose value is still None (the placeholders in data/card33_storage.py)
keeps whatever the case has and is reported as a warning.
"""

from ..csvio import DataError
from ..data.card33_storage import CONSTRAINT, STORAGE
from .base import CardError
from .nodes import open_nodes
from .. import report as R

CARD = "33"
SECTION_CONSTRAINTS = "constraints"
SECTION_RHS = "rhs_policy"
TARGET = "system/nodes_*.json"


def apply(ctx):
    option = ctx.option
    if option not in STORAGE:
        raise CardError(
            f"option {option} is not defined for card {CARD}; it has {sorted(STORAGE)}",
            status=R.NOT_IN_DATABASE,
        )

    allowances = STORAGE[option]
    changes = []
    pending = []

    for period, nodes in open_nodes(ctx):
        edited = []
        basins = [b for b in (allowances or {})] or _basins_in_file(nodes)

        for basin in basins:
            value = None if allowances is None else allowances.get(basin)
            if allowances is not None and value is None:
                if basin not in pending:
                    pending.append(basin)
                continue
            try:
                if allowances is None:
                    before, after = nodes.set(basin, CONSTRAINT, False,
                                              section=SECTION_CONSTRAINTS)
                else:
                    nodes.set(basin, CONSTRAINT, True, section=SECTION_CONSTRAINTS)
                    before, after = nodes.set(basin, CONSTRAINT, value, section=SECTION_RHS)
            except DataError as error:
                if ctx.strict:
                    raise
                ctx.report.warn(f"[{CARD}] {error}")
                continue
            if before != after:
                edited.append(basin)

        if nodes.changed:
            ctx.save(nodes)
            changes.append({
                "file": ctx.relative(nodes.path),
                "period": period,
                "basins": edited,
            })

    if pending:
        ctx.report.warn(
            f"[{CARD}] option {option}: no value yet for {', '.join(pending)}; "
            f"those basins kept the value the case had"
        )

    if allowances is not None and not any(v is not None for v in allowances.values()):
        raise CardError(
            f"option {option} has no value defined yet; the case kept its allowances",
            status=R.NOT_IN_DATABASE,
        )

    if not changes:
        ctx.unchanged(TARGET, detail=f"storage already set for option {option}")
        return

    how = "constraint turned off" if allowances is None else "allowance per basin"
    ctx.applied(TARGET, detail=f"{len(changes)} period file(s), {how}", changes=changes)


def _basins_in_file(nodes):
    """Used by option a, which has no value table of its own."""
    from ..data.card33_storage import BASINS

    return [b for b in BASINS if f'"id": "{b}"' in nodes.text]
