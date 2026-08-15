"""Variable 29 - Nuclear power plants.

    a  No life extensions or new capacity
    b  Life extensions, but no new capacity
    c  Life extension and new capacity allowed with MaxCapacityConstraint

Only two of the 56 rows in nuclear_power.csv are real plants, Angra 1 and
Angra 2. The rest are candidates for new capacity, one per state.

    a   the two Angras run out their remaining life and candidate rows are removed.
    b   the Angras get a 35 year extension counted from 2025; candidates are removed.
    c   same extension; candidates remain available and expansible.

Every retained row has has_capacity TRUE. An Angra whose remaining lifetime is
zero keeps has_capacity TRUE but has MinFlowConstraint FALSE.

Remaining lifetime, in years, written on the Angra rows only:

            2025  2030  2035  2040  2045  2050
    a  A1     16    11     6     1     0     0
       A2     19    14     9     4     0     0
    b/c A1    35    30    25    20    15    10
       A2     35    30    25    20    15    10

The default nuclear CSVs do not carry the MaxCapacityConstraint flag, so this
card adds it. The numerical max_capacity still has to be supplied separately;
without it Macro uses its default of infinity.
"""

from .flags import DROP, FALSE, TRUE, apply_plan, check_option

CARD = "29"
ANGRA_IDS = ("angra1", "angra2")

# Spreadsheet positions, for reference: 4, 12, 14.
MIN_FLOW = "edges--elec_edge--constraints--MinFlowConstraint"
CAN_EXPAND = "edges--elec_edge--can_expand"
HAS_CAPACITY = "edges--elec_edge--has_capacity"
LIFETIME = "edges--elec_edge--lifetime"
MAX_CAPACITY_CONSTRAINT = "edges--elec_edge--constraints--MaxCapacityConstraint"

FILE = "nuclear_power.csv"

LIFETIME_BY_OPTION = {
    "A": {
        2025: {"angra1": 16, "angra2": 19},
        2030: {"angra1": 11, "angra2": 14},
        2035: {"angra1": 6, "angra2": 9},
        2040: {"angra1": 1, "angra2": 4},
        2045: {"angra1": 0, "angra2": 0},
        2050: {"angra1": 0, "angra2": 0},
    },
    "B": {
        2025: {"angra1": 35, "angra2": 35},
        2030: {"angra1": 30, "angra2": 30},
        2035: {"angra1": 25, "angra2": 25},
        2040: {"angra1": 20, "angra2": 20},
        2045: {"angra1": 15, "angra2": 15},
        2050: {"angra1": 10, "angra2": 10},
    },
}
LIFETIME_BY_OPTION["C"] = LIFETIME_BY_OPTION["B"]


def which_angra(asset_id):
    lowered = asset_id.lower()
    return next((name for name in ANGRA_IDS if lowered.endswith(name)), None)


def build_rule(ctx):
    """The rule for the chosen option: (asset_id, period) -> {column: value}."""
    option = ctx.option
    lifetimes = LIFETIME_BY_OPTION[option]

    def rule(asset_id, period):
        angra = which_angra(asset_id)
        by_period = lifetimes.get(period, {})
        if angra:
            lifetime = by_period.get(angra)
            on = lifetime is None or lifetime > 0
            values = {
                MIN_FLOW: TRUE if on else FALSE,
                CAN_EXPAND: FALSE,
                HAS_CAPACITY: TRUE,
                MAX_CAPACITY_CONSTRAINT: FALSE,
            }
            if lifetime is not None:
                values[LIFETIME] = lifetime
            return values

        if option == "C":
            return {
                MIN_FLOW: TRUE,
                HAS_CAPACITY: TRUE,
                CAN_EXPAND: TRUE,
                MAX_CAPACITY_CONSTRAINT: TRUE,
            }
        return DROP

    return rule


def apply(ctx):
    check_option(ctx, CARD, LIFETIME_BY_OPTION)
    rule = build_rule(ctx)

    apply_plan(
        ctx,
        CARD,
        {FILE: rule},
        f"assets/**/{FILE}",
        new_columns={FILE: {MAX_CAPACITY_CONSTRAINT: FALSE}},
    )
