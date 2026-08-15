"""macro_scenario - applies the platform's scenario choices to a Macro case.

    from macro_scenario import apply_scenario_config
    report = apply_scenario_config(job_id, "scenario_config.csv", case_dir)

See README.md for the layout and for how to add a card.
"""

from .apply import apply_scenario_config
from .scenario_config import Answer, read_scenario_config

__all__ = ["apply_scenario_config", "read_scenario_config", "Answer"]
__version__ = "0.1.0"
