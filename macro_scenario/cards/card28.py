"""Variable 28 - Fossil thermal power plants.

    a  New coal and gas available
    b  No new coal; new gas available without MaxCapacityConstraint
    c  No new coal; new gas available with MaxCapacityConstraint
    d  No new coal or gas

Four files, each with two kinds of row: the plants that already exist, whose id
ends in _Existing (optionally followed by a number, e.g. _Existing_1,
_Existing_2, for multiple existing plants at the same location), and the
candidates for new capacity.

Existing plants are always retained with can_expand FALSE and has_capacity
TRUE. Candidate rows are either retained with can_expand and has_capacity TRUE,
or removed from the working CSV altogether.

              new coal     new natural gas     gas capacity cap
    a         retained     retained            unchanged
    b         removed      retained            constraint FALSE
    c         removed      retained            constraint TRUE and max_capacity 5000
    d         removed      removed             unchanged on the existing plants

In option c, MaxCapacityConstraint and max_capacity apply only to new (retained
candidate) gas rows. Existing plants never have either value written to them
and keep whatever was already in the working CSV. If either column is absent,
this card adds it to the working CSV.

natural_gas_power_ccs has no _Existing row at all, which is correct: there is no
gas plant with CCS in Brazil today. Every row there takes the candidate branch.
"""

import re

from .flags import DROP, FALSE, TRUE, apply_plan, check_option

CARD = "28"
EXISTING_SUFFIX = "_existing"
# Matches "..._existing" as well as "..._existing_<number>" (e.g. the numbered
# suffixes used to disambiguate multiple existing plants at the same location).
EXISTING_PATTERN = re.compile(re.escape(EXISTING_SUFFIX) + r"(_\d+)?$", re.IGNORECASE)

# Spreadsheet positions, for reference: 12 and 14 in the original files.
CAN_EXPAND = "edges--elec_edge--can_expand"
HAS_CAPACITY = "edges--elec_edge--has_capacity"
MAX_CAPACITY_CONSTRAINT = "edges--elec_edge--constraints--MaxCapacityConstraint"
MAX_CAPACITY = "edges--elec_edge--max_capacity"

COAL = "coal_power.csv"
GAS = ["natural_gas_power_cc.csv", "natural_gas_power_sc.csv", "natural_gas_power_ccs.csv"]

BEHAVIOUR = {
    "A": {"coal": True, "gas": True, "gas_constraint": None, "gas_capacity": None},
    "B": {"coal": False, "gas": True, "gas_constraint": FALSE, "gas_capacity": None},
    "C": {"coal": False, "gas": True, "gas_constraint": TRUE, "gas_capacity": 5000},
    "D": {"coal": False, "gas": False, "gas_constraint": None, "gas_capacity": None},
}


def is_existing(asset_id):
    return EXISTING_PATTERN.search(asset_id) is not None


def rule_for(allow_candidates, max_constraint=None, max_capacity=None):
    def rule(asset_id, period):
        if is_existing(asset_id):
            # Existing plants keep can_expand FALSE / has_capacity TRUE only.
            # MaxCapacityConstraint and max_capacity are never written here,
            # regardless of option, so their pre-existing values are untouched.
            return {CAN_EXPAND: FALSE, HAS_CAPACITY: TRUE}
        if not allow_candidates:
            return DROP
        values = {CAN_EXPAND: TRUE, HAS_CAPACITY: TRUE}
        if max_constraint is not None:
            values[MAX_CAPACITY_CONSTRAINT] = max_constraint
        if max_capacity is not None:
            values[MAX_CAPACITY] = max_capacity
        return values

    return rule


def apply(ctx):
    check_option(ctx, CARD, BEHAVIOUR)
    behaviour = BEHAVIOUR[ctx.option]

    plan = {COAL: rule_for(behaviour["coal"])}
    for filename in GAS:
        plan[filename] = rule_for(
            behaviour["gas"],
            behaviour["gas_constraint"],
            behaviour["gas_capacity"],
        )

    new_columns = {}
    if behaviour["gas_constraint"] is not None:
        new_columns = {
            filename: {MAX_CAPACITY_CONSTRAINT: FALSE}
            for filename in GAS
        }
    if behaviour["gas_capacity"] is not None:
        for filename in GAS:
            new_columns[filename][MAX_CAPACITY] = behaviour["gas_capacity"]
    apply_plan(
        ctx,
        CARD,
        plan,
        "assets/**/{coal,natural_gas}_power*.csv",
        new_columns=new_columns,
    )
