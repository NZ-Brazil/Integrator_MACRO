"""Variable 25 - Energy supply technology innovation (a Slower / b Mid-range / c Faster).

The option sets how fast supply technologies get cheaper. In the case it is a
pair of cost columns per technology - investment_cost and fixed_om_cost, plus
the storage equivalents - held in assets_full/ under the suffixes _25-A, _25-B
and _25-C, and copied over the base columns of assets/.

This card runs first in the integrator: it rewrites the largest number of asset
files, and later cards (capacity caps, technology availability) edit a subset of
those same files. Running it last would undo them.
"""

from . import suffix

CARD = "25"


def apply(ctx):
    suffix.apply_card(ctx, CARD)
