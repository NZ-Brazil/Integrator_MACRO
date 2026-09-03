"""Command line front end, for running the integrator by hand.

    python -m macro_scenario CASE                          # reads CASE/scenario_config.csv
    python -m macro_scenario CASE -c scenario_config.csv
    python -m macro_scenario CASE -c config.csv --check    # dry run, writes nothing
    python -m macro_scenario CASE --set 25=b --set 24=b    # no csv, for testing one card
    python -m macro_scenario CASE -c config.csv --report adjustments.json
    python -m macro_scenario CASE -c config.csv --ep2macro "MACRO input"
    python -m macro_scenario CASE -c config.csv --ep2macro "MACRO input" --tdr

    --catalog variables_catalog.json   checks the answers against the catalog
    --strict                           stop at the first problem instead of warning
"""

import argparse
import json
import sys

from .apply import apply_scenario_config
from .scenario_config import Answer, read_scenario_config


def parse_set(values):
    answers = []
    for item in values:
        variable, _, option = item.partition("=")
        if not option:
            raise SystemExit(f"--set expects VARIABLE=OPTION, got '{item}'")
        answers.append(
            Answer(variable_id=int(variable), option_id=option.strip().upper(),
                   variable_name=f"variable {variable}")
        )
    return answers


def main(argv=None):
    parser = argparse.ArgumentParser(prog="macro_scenario", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("case", help="case directory (the one with run.jl)")
    parser.add_argument("-c", "--config", help=f"scenario_config.csv (default: <case>/scenario_config.csv)")
    parser.add_argument("--set", action="append", default=[], metavar="ID=OPTION",
                        help="answer one variable inline, e.g. --set 25=b")
    parser.add_argument("--job-id", default="local", help="job id recorded in the report")
    parser.add_argument("--check", action="store_true", help="dry run: report without writing")
    parser.add_argument("--strict", action="store_true", help="raise instead of warning")
    parser.add_argument("--catalog", help="variables_catalog.json, to validate the answers")
    parser.add_argument("--report", nargs="?", const=True, default=False, metavar="PATH",
                        help="write the adjustment report (default: <case>/adjustments.json)")
    parser.add_argument("--ep2macro", metavar="DIR",
                        help="EP2MACRO output folder: copies the demand files into system/ "
                             "and writes CO2_Emissions into co2_source")
    parser.add_argument("--tdr", action="store_true",
                        help="run run_tdr.jl at the end (needs julia on PATH)")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args(argv)

    config = parse_set(args.set) if args.set else (args.config or args.case)
    report = apply_scenario_config(
        job_id=args.job_id,
        scenario_config=config,
        case_dir=args.case,
        logger=(lambda message: None) if args.quiet else print,
        strict=args.strict,
        dry_run=args.check,
        catalog=args.catalog,
        write_report=args.report,
        ep2macro_dir=args.ep2macro,
        run_tdr=args.tdr,
    )

    if args.quiet:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
