"""apply_scenario_config - the single entry point the worker calls.

    from macro_scenario import apply_scenario_config

    report = apply_scenario_config(
        job_id="3f2b...",                       # uuid of the job
        scenario_config="scenario_config.csv",  # path, list of rows, or None
        case_dir="/data/case",                  # case already extracted
        ep2macro_dir="/data/MACRO input",       # optional: converter output
        run_tdr=True,                           # optional: reduce at the end
    )

Order of operations:

    1  card 25                     costs in assets/
    2  EP2MACRO import             demand files into system/, CO2_Emissions
                                   into co2_source of every nodes_<period>.json
       system cards                caps (2), CO2 storage (33), fuel prices (24)
    3  asset cards                 solar and wind limits (30), and the rest
    4  TDR                         reduces every series in system/ together

The case is modified in place. Nothing is downloaded and nothing is published -
that stays with the worker, which posts the returned report to
POST /internal/jobs/{id}/adjustments.

A card writes all of its files or none of them: the edits are staged in memory
and flushed once the handler returns cleanly, so a card that fails halfway leaves
the case exactly as it was rather than half applied.

Contract (Padroes.md, section 3):
  - in place, idempotent, never brings the job down over missing data
  - an empty or absent config returns status "skipped" without touching the case
  - variables that belong to other models are ignored, except when a Macro card
    reads them to decide its own option - see ctx.chosen() and card 30 / card 6
  - strict=True turns every warning into an exception, for use in tests
"""

from pathlib import Path

from . import report as R
from .cards import STAGES, base, handler, needs_option, sort_key, stage_of
from .csvio import DataError
from .scenario_config import (
    CONFIG_FILENAME,
    check_against_catalog,
    load_catalog,
    read_scenario_config,
)
from .steps import ep2macro, tdr

REPORT_FILENAME = "adjustments.json"


def apply_scenario_config(
    job_id,
    scenario_config=None,
    case_dir=".",
    logger=print,
    strict=False,
    dry_run=False,
    catalog=None,
    write_report=False,
    ep2macro_dir=None,
    run_tdr=False,
    options=None,
):
    """Apply the user's scenario choices to a Macro case. Returns the report dict."""
    case_dir = Path(case_dir).resolve()
    if not case_dir.is_dir():
        raise FileNotFoundError(f"case not found: {case_dir}")

    report = R.Report(job_id, logger=logger)

    if scenario_config is None:
        scenario_config = case_dir / CONFIG_FILENAME
    answers = read_scenario_config(scenario_config)
    report.variables_received = len(answers)

    if not answers and not ep2macro_dir and not run_tdr:
        report.log(f"no {CONFIG_FILENAME}: running the case as it is")
        return report.to_dict()

    if catalog and answers:
        for problem in check_against_catalog(answers, load_catalog(catalog)):
            report.warn(problem)

    mine = [a for a in answers if handler(a.variable_id)]
    theirs = [a for a in answers if not handler(a.variable_id)]
    if theirs:
        report.note("not consumed by Macro: " + ", ".join(str(a.variable_id) for a in theirs))

    report.log(
        f"macro-energy: {len(answers)} variable(s) received, {len(mine)} consumed"
        + (" (check only, nothing written)" if dry_run else "")
    )

    # Every answer received, not just the ones Macro owns a card for: card 30
    # reads card 6 through this even though Macro has no card6.py of its own.
    chosen = {a.variable_id: a for a in answers}

    def run_stage(stage):
        for answer in sorted([a for a in mine if stage_of(a.variable_id) == stage], key=sort_key):
            _run_card(answer, case_dir, report, dry_run, strict, options, chosen)

    run_stage(STAGES[0])                                   # 1. costs in assets/
    _import_ep2macro(case_dir, ep2macro_dir, report, dry_run, strict)   # 2.1
    run_stage(STAGES[1])                                   # 2.2 system cards
    run_stage(STAGES[2])                                   # 3. remaining asset cards
    if run_tdr:
        _run_tdr(case_dir, report, dry_run, strict)        # 4. TDR

    counted = report.counts()
    report.log(
        f"macro-energy: {counted[R.APPLIED]} applied, {counted[R.UNCHANGED]} unchanged, "
        f"{len(report.warnings)} warning(s)"
    )

    result = report.to_dict()
    if write_report and not dry_run:
        path = Path(write_report) if isinstance(write_report, (str, Path)) else case_dir / REPORT_FILENAME
        report.write(path)
        report.log(f"report written to {path}")
    return result


# -- one card ------------------------------------------------------------


def _run_card(answer, case_dir, report, dry_run, strict, options, chosen=None):
    ctx = base.Context(
        case_dir=case_dir,
        answer=answer,
        report=report,
        dry_run=dry_run,
        strict=strict,
        options=dict(options or {}),
        answers=dict(chosen or {}),
    )
    if needs_option(answer.variable_id) and not answer.is_slider and not answer.option_id:
        report.add(answer, R.NOT_IMPLEMENTED, detail="no option marked in the form")
        return
    try:
        handler(answer.variable_id)(ctx)
    except base.CardError as error:
        ctx.discard()
        if strict:
            raise
        report.add(answer, error.status, detail=str(error))
        return
    except DataError as error:
        ctx.discard()
        if strict:
            raise
        report.add(answer, R.KEY_MISSING, detail=str(error))
        return
    except Exception as error:  # unexpected: report, do not stop the job
        ctx.discard()
        if strict:
            raise
        report.add(answer, R.KEY_MISSING, detail=f"{type(error).__name__}: {error}")
        report.warn(f"[{answer.variable_id}] unexpected error: {type(error).__name__}: {error}")
        return

    # The card finished: everything it staged goes to disk together.
    ctx.flush()


# -- the steps that are not form variables -------------------------------


def _import_ep2macro(case_dir, ep2macro_dir, report, dry_run, strict):
    if not ep2macro_dir:
        return
    source = Path(ep2macro_dir)
    if not source.is_dir():
        message = f"EP2MACRO output not found: {source}"
        if strict:
            raise FileNotFoundError(message)
        report.warn(message)
        return

    try:
        copied = ep2macro.copy_demand_files(case_dir, source, dry_run=dry_run)
        report.step("ep2macro_demand", f"{len(copied)} demand file(s) copied into system/",
                    files=copied)
    except DataError as error:
        if strict:
            raise
        report.warn(f"[ep2macro] {error}")

    emissions_path = source / ep2macro.EMISSIONS_FILENAME
    if not emissions_path.is_file():
        report.warn(f"[ep2macro] {ep2macro.EMISSIONS_FILENAME} not found in {source}")
        return
    try:
        emissions = ep2macro.read_emissions(emissions_path)
        changes = ep2macro.write_emissions(
            case_dir, emissions, dry_run=dry_run,
            warn=lambda message: report.warn(f"[ep2macro] {message}"),
        )
        report.step(
            "ep2macro_co2_source",
            f"co2_source max_supply set in {len(changes)} period file(s) from "
            f"{ep2macro.EMISSIONS_FILENAME}",
            changes=changes,
        )
    except DataError as error:
        if strict:
            raise
        report.warn(f"[ep2macro] {error}")


def _run_tdr(case_dir, report, dry_run, strict):
    if dry_run:
        report.step("tdr", "skipped: check only")
        return
    ok, message = tdr.run(case_dir)
    report.step("tdr", message)
    if not ok:
        if strict:
            raise RuntimeError(message)
        report.warn(f"[tdr] {message}")
