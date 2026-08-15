"""Run the integrator on one case, from the editor.

Open this file in VS Code and press F5 (or Run > Run Without Debugging). Edit
the four settings below first. Nothing here is needed in production - the worker
calls apply_scenario_config() directly - this is just a comfortable way to try a
scenario out and read the report.

Requires Python 3.8 or newer and nothing else: the package only uses the
standard library.
"""

import json
from pathlib import Path

from macro_scenario import apply_scenario_config

# -- settings ------------------------------------------------------------

CASE = Path("../NZB_Default_Scenario")   # the case folder, the one with run.jl
CONFIG = CASE / "scenario_config.csv"    # what the platform produced
EP2MACRO = None                          # e.g. Path("../MACRO input"), or None
CHECK_ONLY = True                        # True: report without touching the case

# -- run -----------------------------------------------------------------

if __name__ == "__main__":
    report = apply_scenario_config(
        job_id="local-test",
        scenario_config=CONFIG,
        case_dir=CASE,
        ep2macro_dir=EP2MACRO,
        dry_run=CHECK_ONLY,
        write_report=not CHECK_ONLY,
    )

    print()
    print(json.dumps(report["summary"], indent=2))
    for warning in report["warnings"]:
        print(f"warning: {warning}")
