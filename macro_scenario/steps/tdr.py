"""Step 4 - Time Domain Reduction, at the very end.

run_tdr.jl discovers every 8760-row csv in system/, backs the folder up to
system_full/, clusters, and reduces all series in place onto the same
representative weeks. Running it last is what keeps demand, availability and
fuel prices on one and the same period map: every card has already written its
values into the full series by then.

The TDR is Julia, so this step shells out. It is off by default - the worker may
prefer to run it as its own stage - and it is not run in dry-run mode.

run_tdr.jl (and its Project.toml / Manifest.toml) live ONCE, next to the
integrator itself - not duplicated into every case copy. Julia activates that
shared environment (--project=<integrator dir>) and is pointed at the case
directory as its only argument, exactly like before.
"""

import shutil
import subprocess
from pathlib import Path

SCRIPT_NAME = "run_tdr.jl"

# macro_scenario/steps/tdr.py -> macro_scenario/steps -> macro_scenario -> Integrator_MACRO-main
INTEGRATOR_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPT = INTEGRATOR_DIR / SCRIPT_NAME

DEFAULT_TIMEOUT = 3 * 60 * 60  # the clustering is not fast


def available(case_dir=None):
    """True if run_tdr.jl (next to the integrator) and julia are both ready to go.

    case_dir is accepted for backward compatibility with earlier callers but is
    no longer needed: the script's location doesn't depend on the case.
    """
    return SCRIPT.is_file() and shutil.which("julia") is not None


def run(case_dir, timeout=DEFAULT_TIMEOUT, julia="julia"):
    """Run the shared run_tdr.jl over one case. Returns (ok, message)."""
    if not SCRIPT.is_file():
        return False, f"{SCRIPT_NAME} not found next to the integrator ({INTEGRATOR_DIR})"
    if shutil.which(julia) is None:
        return False, f"'{julia}' is not on PATH"

    command = [julia, f"--project={INTEGRATOR_DIR}", str(SCRIPT), str(case_dir)]
    try:
        finished = subprocess.run(
            command, cwd=str(case_dir), capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return False, f"{SCRIPT_NAME} did not finish within {timeout}s"

    if finished.returncode != 0:
        tail = (finished.stderr or finished.stdout or "").strip().splitlines()[-5:]
        return False, f"{SCRIPT_NAME} exited with {finished.returncode}: {' / '.join(tail)}"
    return True, f"{SCRIPT_NAME} finished"
