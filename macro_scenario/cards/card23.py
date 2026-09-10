"""Variable 23 - Fossil fuel utilization.

    a  continued fossil fuel use is allowed   -> supply left unrestricted
    b  fossil gasoline and diesel eliminated by 2050

Target, in every period file:

    system/nodes_<period>.json
        gasoline_fossil_BR -> max_supply
        diesel_fossil_BR   -> max_supply

WHY THESE TWO NODES AND NOTHING ELSE

Fossil gasoline and diesel reach final demand by two parallel routes, and both
start at the same supply node:

    <fuel>_fossil_BR -> GeneralFuelsEndUse                   -> burnt, accounted
    <fuel>_fossil_BR -> FossilFuelsUpstream -> <fuel>_demand_BR

The second route is the one the outputs package documents as ressalva A1 (only
the refining CO2 is booked, the combustion of the volume it delivers is booked
nowhere). That is an accounting problem, not a supply one: the volume still
comes through <fuel>_fossil_BR. So capping this one node closes both routes,
including the flexfuel demand, which is why the card does not have to touch the
mandate nodes or the FossilFuelsUpstream rows.

jetfuel_fossil_BR is left alone: the card is gasoline and diesel.

The card also does not touch the power system, and does not need to: gasoline
and diesel do not generate electricity in this case. That matches the note on
the card, which says the restriction must not stop fossil fuels being used for
electricity generation.

MAX_SUPPLY IS PER TIME STEP, NOT PER YEAR

From src/model/networks/node.jl, the bound is written once for every time step:

    max_sf = max_supply(n, s, t)
    @constraint(model, sf <= max_sf)

and a one-element "max_supply": [ x ] applies that same x to every t. The annual
quantity is the weighted sum over the time steps, so

    annual ceiling = max_supply x TotalHoursModeled / HoursPerTimeStep

which is 8760 in this case (system/time_data.json: TotalHoursModeled 8760,
HoursPerTimeStep 1 for LiquidFuels). Confirmed against the case: co2_source
carries max_supply 37.935,80, i.e. 332,3 Mt/year, and the S5 run delivers
327,4 Mt from it in 2040 - 98,5% of that ceiling.

Getting this factor wrong is a silent failure: too large and the card does
nothing, too small and the run is infeasible. The card reads the two numbers
from time_data.json and falls back to 8760/1 only if the file is absent.

THE TRAJECTORY IS A SHARE OF THE PERIOD'S DEMAND

Rather than absolute volumes, data/card23_supply.py holds a share per period and
the card multiplies it by the annual demand read from the demand nodes of that
same file. The trajectory then follows whatever EnergyPathways sent, and no
absolute number goes stale in the database.

WHAT HAS TO MAKE UP THE DIFFERENCE, AND WHY THE CARD ONLY REPORTS IT

The demand nodes carry AggregatedDemandConstraint, which is hard: squeezing the
fossil ceiling without a substitute makes the case infeasible rather than
expensive. But the substitute has no guaranteed floor the card could check
against, so there is no arithmetic feasibility test to run here. Measured on the
S5 run, 2040:

    diesel_demand_BR      <- diesel_fossil_BR 395,7 + renewable_diesel_BR 247,2
    flexfuel_demand_BR    <- ethanol_BR 242,1 (already all renewable)
    gasoline_demand_BR    <- gasoline_fossil_BR 37,9 + gasoline_renewable_BR 0,2

    biodiesel_mandate_demand_BR is a SEPARATE demand node, fed by biodiesel_BR.
    It does not substitute inside diesel_demand_BR and must not be counted as
    headroom for it.

So the card reports, per period and per fuel, how much the substitute route has
to deliver for the case to solve, and names that route. It never refuses to
write: whether the route can scale is a question about the case, not about the
option the user picked.

Worth knowing before reading the results: renewable_diesel_BR is produced almost
entirely by BECCSATJ, which runs on ethanol, which runs on sugarcane. Squeezing
fossil diesel therefore pushes the model towards more sugarcane - and both of
those routes carry known carbon-accounting ressalvas (A2 on the cane's
co2_content, and the ATJ booking the ethanol's uptake a second time). The
emissions curve of a card 23 = B run will improve partly for that reason, not
only because the fossil volume went away.

To make the substitute compulsory instead of merely permitted, the next step is
to raise biodiesel_mandate_demand_BR -> AggregatedDemandConstraint as the diesel
ceiling drops. That is one more write in this same loop and is deliberately NOT
done here: it changes a number the team set, and that is their call.
"""

import json

from ..csvio import DataError
from ..data.card23_supply import FUELS, SHARE, UNRESTRICTED
from .base import CardError
from .nodes import open_nodes
from .. import report as R

CARD = "23"
TARGET = "system/nodes_*.json"
SUPPLY_KEY = "max_supply"
DEMAND_KEY = "AggregatedDemandConstraint"

# The case writes this section with two different capitalizations - CMOUT on the
# diesel and gasoline nodes, CMout on the jet fuel mandate ones. Try both, and
# the plain rhs_policy as a last resort.
DEMAND_SECTIONS = ("CMOUT_rhs_policy", "CMout_rhs_policy", "rhs_policy")

TIME_DATA = ("system", "time_data.json")
COMMODITY = "LiquidFuels"
DEFAULT_HOURS = 8760
DEFAULT_HOURS_PER_STEP = 1


def apply(ctx):
    option = ctx.option
    if option not in SHARE:
        raise CardError(
            f"option {option} is not defined for card {CARD}; it has {sorted(SHARE)}",
            status=R.NOT_IN_DATABASE,
        )

    shares = SHARE[option]
    steps = steps_per_year(ctx)
    changes = []
    notes = []

    for period, nodes in open_nodes(ctx):
        if shares is not None and period not in shares:
            ctx.report.warn(
                f"[{CARD}] period {period} has no share in the trajectory; "
                f"{ctx.relative(nodes.path)} kept its own ceiling"
            )
            continue

        edited = []
        for supply_node, fuel in FUELS.items():
            try:
                if shares is None:
                    value = UNRESTRICTED
                else:
                    demand = total_demand(nodes, fuel["demand"])
                    value = shares[period] * demand / steps
                    notes.append(gap(fuel, value * steps, demand, period))
                before, after = nodes.set_list(supply_node, SUPPLY_KEY, value)
            except DataError as error:
                if ctx.strict:
                    raise
                ctx.report.warn(f"[{CARD}] {error}")
                continue
            if before != after:
                edited.append(supply_node)

        if nodes.changed:
            ctx.save(nodes)
            changes.append({
                "file": ctx.relative(nodes.path),
                "period": period,
                "nodes": edited,
            })

    for note in notes:
        if note:
            ctx.note(f"[{CARD}] {note}")

    if not changes:
        ctx.unchanged(TARGET, detail=f"fossil supply already set for option {option}")
        return

    how = "unrestricted" if shares is None else "declining ceiling to zero in 2050"
    ctx.applied(TARGET, detail=f"{len(changes)} period file(s), {how}", changes=changes)


# -- reading the case ----------------------------------------------------


def steps_per_year(ctx):
    """TotalHoursModeled / HoursPerTimeStep, i.e. how many times the per-time-step
    max_supply is counted in a year. 8760 in this case."""
    path = ctx.path(*TIME_DATA)
    if not path.is_file():
        ctx.report.warn(
            f"[{CARD}] {'/'.join(TIME_DATA)} not found; assuming "
            f"{DEFAULT_HOURS} time step(s) per year"
        )
        return DEFAULT_HOURS
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    total = data.get("TotalHoursModeled", DEFAULT_HOURS)
    per_step = data.get("HoursPerTimeStep", {})
    if isinstance(per_step, dict):
        per_step = per_step.get(COMMODITY, DEFAULT_HOURS_PER_STEP)
    per_step = per_step or DEFAULT_HOURS_PER_STEP
    steps = total / per_step
    if steps <= 0:
        raise CardError(
            f"{'/'.join(TIME_DATA)}: TotalHoursModeled {total} and "
            f"HoursPerTimeStep {per_step} give no time step per year"
        )
    return steps


def annual_demand(nodes, node_id):
    """The AggregatedDemandConstraint of a demand node, in the case's annual unit."""
    for section in DEMAND_SECTIONS:
        try:
            return float(nodes.get(node_id, DEMAND_KEY, section=section))
        except DataError:
            continue
    raise DataError(
        f"{nodes.path.name}: node '{node_id}' has no {DEMAND_KEY} in any of "
        f"{', '.join(DEMAND_SECTIONS)}"
    )


def total_demand(nodes, node_ids):
    return sum(annual_demand(nodes, node_id) for node_id in node_ids)


def gap(fuel, ceiling, demand, period):
    """How much the substitute route has to deliver for the case to solve, as a
    line for the report. None while the ceiling still covers the whole demand."""
    missing = demand - ceiling
    if missing <= 0:
        return None
    return (
        f"period {period}: the ceiling covers {ceiling:,.0f} of a demand of "
        f"{demand:,.0f}; the remaining {missing:,.0f} has to come from "
        f"{fuel['substitute']}"
    )
