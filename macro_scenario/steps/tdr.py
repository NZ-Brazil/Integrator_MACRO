"""Step 4 - Time Domain Reduction, at the very end.

run_tdr.jl discovers every 8760-row csv in system/, backs the folder up to
system_full/, clusters, and reduces all series in place onto the same
representative weeks. Running it last is what keeps demand, availability and
fuel prices on one and the same period map: every card has already written its
values into the full series by then.

The TDR is Julia, so this step shells out. It is off by default - the worker may
prefer to run it as its own stage - and it is not run in dry-run mode.
"""

import shutil
import subprocess

SCRIPT = "run_tdr.jl"
DEFAULT_TIMEOUT = 3 * 60 * 60  # the clustering is not fast


def available(case_dir):
    return (case_dir / SCRIPT).is_file() and shutil.which("julia") is not None


def run(case_dir, timeout=DEFAULT_TIMEOUT, julia="julia"):
    """Run run_tdr.jl over the case. Returns (ok, message)."""
    script = case_dir / SCRIPT
    if not script.is_file():
        return False, f"{SCRIPT} not found in the case"
    if shutil.which(julia) is None:
        return False, f"'{julia}' is not on PATH"

    command = [julia, f"--project={case_dir}", str(script), str(case_dir)]
    try:
        finished = subprocess.run(
            command, cwd=str(case_dir), capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return False, f"{SCRIPT} did not finish within {timeout}s"

    if finished.returncode != 0:
        tail = (finished.stderr or finished.stdout or "").strip().splitlines()[-5:]
        return False, f"{SCRIPT} exited with {finished.returncode}: {' / '.join(tail)}"
    return True, f"{SCRIPT} finished"
