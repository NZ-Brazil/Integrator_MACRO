"""Variable 31 - Rooftop solar deployment.

    a  Reference   b  Medium   c  High

rooftop_pv.csv holds the same 27 regions three times over: the reference rows,
and two blocks of mandatory deployment whose ids end in _mandatoryB and
_mandatoryC. Exactly one block remains in the working file; the other two are
removed.

    option a  -> keep the plain rows
    option b  -> keep the _mandatoryB rows
    option c  -> keep the _mandatoryC rows

Every retained row has can_expand and has_capacity TRUE.  The minimum-capacity
flag is FALSE for the reference option and TRUE for the two mandatory options.
The numeric min_capacity already stored in the selected row is never changed.
"""

from .flags import DROP, TRUE, apply_plan, check_option

CARD = "31"
FILE = "rooftop_pv.csv"

# Columns edited by the card.  min_capacity is intentionally not listed: each
# scenario row already carries the correct numeric value in the database.
CAN_EXPAND = "edges--edge--can_expand"
HAS_CAPACITY = "edges--edge--has_capacity"
MIN_CAPACITY_CONSTRAINT = "edges--edge--constraints--MinCapacityConstraint"

MANDATORY = {"B": "_mandatoryb", "C": "_mandatoryc"}
ACTIVE_BLOCK = {"A": None, "B": "B", "C": "C"}  # None means the plain rows


def block_of(asset_id):
    """'B', 'C', or None for a plain row."""
    lowered = asset_id.lower()
    return next((name for name, suffix in MANDATORY.items() if lowered.endswith(suffix)), None)


def apply(ctx):
    check_option(ctx, CARD, ACTIVE_BLOCK)
    active = ACTIVE_BLOCK[ctx.option]

    def rule(asset_id, period):
        if block_of(asset_id) != active:
            return DROP
        return {
            CAN_EXPAND: TRUE,
            HAS_CAPACITY: TRUE,
            MIN_CAPACITY_CONSTRAINT: TRUE if active else "FALSE",
        }

    apply_plan(ctx, CARD, {FILE: rule}, f"assets/**/{FILE}")
