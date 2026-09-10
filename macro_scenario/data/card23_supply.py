"""Card 23 - Fossil fuel utilization: how much fossil supply stays available.

Source: the card Option B says "fossil gasoline and diesel eliminated by
2050" without naming an intermediate path: a straight line from the
unrestricted case to zero, one step per period. Change it here, not in the card.

The numbers are SHARES OF THE PERIOD'S OWN DEMAND, not absolute volumes. The
card multiplies them by the annual demand it reads from the demand nodes of that
same period file, so the trajectory recalibrates itself whenever EnergyPathways
changes the demand and no absolute number goes stale here.

Option A leaves the case unrestricted. It still writes, so moving A <-> B is
symmetric (same reason as card 33): a card that writes nothing cannot undo what
the other option wrote.
"""

# The value the case ships with on gasoline_fossil_BR and diesel_fossil_BR. It
# is a placeholder for "no limit": at 8760 h/year it allows 876.000 TWh, three
# orders of magnitude above any demand in the case. Option A restores it.
UNRESTRICTED = 100_000_000

SHARE = {
    # A: unrestricted - the case's own placeholder, whatever the demand is.
    "A": None,
    # B: share of the period's demand that fossil supply may still cover.
    "B": {
        2025: 1.00,
        2030: 0.80,
        2035: 0.60,
        2040: 0.40,
        2045: 0.20,
        2050: 0.00,
    },
}

# Per fossil supply node: the demand nodes it feeds, which anchor the trajectory,
# and the node that has to make up the difference, which is named in the report
# so whoever reads it knows where to look.
#
# jetfuel_fossil_BR is deliberately absent: the card is gasoline and diesel.
#
# Read off the S5 run, 2040: diesel_demand_BR is fed by diesel_fossil_BR (395,7
# TWh) and renewable_diesel_BR (247,2); flexfuel_demand_BR is already fed
# entirely by ethanol_BR (242,1) and gasoline_demand_BR almost entirely by
# gasoline_fossil_BR (37,9 of 38,1).
FUELS = {
    "gasoline_fossil_BR": {
        "demand": ("gasoline_demand_BR", "flexfuel_demand_BR"),
        "substitute": "gasoline_renewable_BR and ethanol_BR",
    },
    "diesel_fossil_BR": {
        "demand": ("diesel_demand_BR",),
        "substitute": "renewable_diesel_BR",
    },
}
