"""Variable 32 - Oil production.

    a  Expansion
    b  Current policies
    c  Production for domestic market only

One column, transforms--emission_rate, on the three upstream rows of
fossil_fuels_upstream.csv, the same in all six periods. The rates are in
data/card32_emissions.py.

Options a and b share the same rates, and they are the ones the case already
carries, so choosing either of them normally reports "unchanged".
"""

from ..data.card32_emissions import EMISSION_RATES
from .flags import apply_plan, check_option

CARD = "32"
FILE = "fossil_fuels_upstream.csv"

# Spreadsheet position, for reference: 14.
EMISSION_RATE = "transforms--emission_rate"


def apply(ctx):
    check_option(ctx, CARD, EMISSION_RATES)
    rates = EMISSION_RATES[ctx.option]

    def rule(asset_id, period):
        rate = rates.get(asset_id)
        return {} if rate is None else {EMISSION_RATE: repr(rate)}

    unknown = [i for i in rates]
    ctx.note(f"[{CARD}] rates written for: {', '.join(unknown)}")
    apply_plan(ctx, CARD, {FILE: rule}, f"assets/**/{FILE}")
