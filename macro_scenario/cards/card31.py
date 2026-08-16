"""Variable 31 - Rooftop solar deployment.

    a  Reference   b  Medium   c  High

rooftop_pv.csv holds the same 27 regions three times over: the reference rows,
and two blocks of mandatory deployment whose ids end in _mandatoryB and
_mandatoryC. Exactly one block remains in the working file; the other two are
removed.

    option a  -> keep the plain rows
    option b  -> keep the _mandatoryB rows
    option c  -> keep the _mandatoryC rows

Every retained candidate row has can_expand and has_capacity TRUE.  The
minimum-capacity flag is FALSE for the reference option and TRUE for the two
mandatory options. The numeric min_capacity already stored in the selected
row is never changed.

The file also carries already-built capacity: ids with "existing" anywhere in
the name (BR_AC_rooftop_pv_existing, and its _existing_mandatoryB /
_existing_mandatoryC repeats, kept only so the file has the same three-block
shape as the rest of the table). These rows go through the same keep/drop
rule as the candidate rows above - one block survives per option - but a kept
existing row is never edited: can_expand, has_capacity and
MinCapacityConstraint stay whatever the row already carries.

    option a  -> keep plain + existing            drop the two _mandatoryB/C blocks
    option b  -> keep _mandatoryB + existing_mandatoryB   drop the rest
    option c  -> keep _mandatoryC + existing_mandatoryC   drop the rest
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

# Unlike card 28's _Existing suffix, an existing id here can be followed by a
# mandatory block too (..._existing_mandatoryb), so this is a plain substring
# test rather than an anchored suffix.
EXISTING = "existing"


def block_of(asset_id):
    """'B', 'C', or None for a plain row."""
    lowered = asset_id.lower()
    return next((name for name, suffix in MANDATORY.items() if lowered.endswith(suffix)), None)


def is_existing(asset_id):
    return EXISTING in asset_id.lower()


def apply(ctx):
    check_option(ctx, CARD, ACTIVE_BLOCK)
    active = ACTIVE_BLOCK[ctx.option]

    def rule(asset_id, period):
        if block_of(asset_id) != active:
            return DROP
        if is_existing(asset_id):
            return None  # already-built capacity: kept, but its flags are left alone
        return {
            CAN_EXPAND: TRUE,
            HAS_CAPACITY: TRUE,
            MIN_CAPACITY_CONSTRAINT: TRUE if active else "FALSE",
        }

    apply_plan(ctx, CARD, {FILE: rule}, f"assets/**/{FILE}")
