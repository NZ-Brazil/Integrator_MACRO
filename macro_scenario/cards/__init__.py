"""Which of the 39 form variables Macro consumes, in which stage, in what order.

This is the Macro equivalent of the variable_map.json used by EnergyPATHWAYS
(Padroes.md, section 6): a variable that is not in HANDLERS is not ours, and is
ignored without a warning.

The stages follow the agreed order of operations:

    1  assets_cost   card 25, which rewrites the cost columns of every asset
    2  (EP2MACRO import: demand files into system/, CO2_Emissions into the nodes)
    2  system        cards that edit system/: the nodes (2, 33) and fuel prices (24)
    3  assets        the remaining asset cards (27, 28, 29, 30, 31, 32)
    4  (TDR: reduces every series in system/ onto one period map)

Card 25 comes first because it rewrites 192 asset files; anything editing those
same files has to come after it. The EP2MACRO import comes before the system
cards because card 2 and the CO2 emissions both write into the node files.

Card 30 is a special case: it is in HANDLERS because it writes to the case, but
the option it acts on is not its own - it reads card 6 through ctx.chosen(6)
instead (see cards/card30.py). Card 6 itself has no card6.py and stays out of
HANDLERS: it belongs to another model and Macro never writes anything for it
directly.

To add a card:
  1. write cards/card<NN>.py with a single `apply(ctx)` function
  2. register it in HANDLERS and give it a stage in STAGE_OF
  3. add it to ORDER if it must run before or after a sibling in the same stage
"""

from . import (card2, card24, card25, card27, card28, card29, card30,
               card31, card32, card33)

HANDLERS = {
    2: card2.apply,
    27: card27.apply,
    28: card28.apply,
    29: card29.apply,
    24: card24.apply,
    25: card25.apply,
    30: card30.apply,
    31: card31.apply,
    32: card32.apply,
    33: card33.apply,
}

ASSETS_COST = "assets_cost"
SYSTEM = "system"
ASSETS = "assets"
STAGES = [ASSETS_COST, SYSTEM, ASSETS]

STAGE_OF = {
    25: ASSETS_COST,
    2: SYSTEM,
    33: SYSTEM,
    24: SYSTEM,
    27: ASSETS,
    28: ASSETS,
    29: ASSETS,
    30: ASSETS,
    31: ASSETS,
    32: ASSETS,
}

ORDER = [25, 2, 33, 24, 27, 28, 29, 30, 31, 32]

# Card 2 is a slider in the form, but Macro ignores the slider and reads the cap
# trajectory csv instead, so it runs even with no option letter marked.
# Card 30 is commanded by card 6 (see cards/card30.py), so its own option letter
# - if the form still sends one - is never read either.
OPTIONLESS = {2, 30}


def handler(variable_id):
    return HANDLERS.get(variable_id)


def needs_option(variable_id):
    return variable_id not in OPTIONLESS


def stage_of(variable_id):
    return STAGE_OF.get(variable_id, ASSETS)


def sort_key(answer):
    """Inside a stage: the ORDER list first, then anything else by variable_id."""
    if answer.variable_id in ORDER:
        return (0, ORDER.index(answer.variable_id), answer.variable_id)
    return (1, 0, answer.variable_id)
