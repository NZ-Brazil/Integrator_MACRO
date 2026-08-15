"""Card 32 - Oil production: upstream emission rate per fuel.

Source: "Scenarios - changing variables in MACRO", sheet Variables, card 32.
The spreadsheet writes them with a decimal comma; here they are floats.

Options a (Expansion) and b (Current policies) carry the same rates on purpose,
and they are the ones already in the case. Only c (production for the domestic
market only) differs. The same rates apply to all six periods.
"""

# tCO2 per unit of fuel, column transforms--emission_rate
EMISSION_RATES = {
    "A": {
       "Gasoline_fossil_Upstream": 0.02021,
        "Diesel_fossil_Upstream": 0.02021,
        "JetFuel_fossil_Upstream": 0.02021,
    },
    "B": {
        "Gasoline_fossil_Upstream": 0.02021,
        "Diesel_fossil_Upstream": 0.02021,
        "JetFuel_fossil_Upstream": 0.02021,
    },
    "C": {
        "Gasoline_fossil_Upstream": 0.02627,
        "Diesel_fossil_Upstream": 0.02705,
        "JetFuel_fossil_Upstream": 0.02627,
    },
}
