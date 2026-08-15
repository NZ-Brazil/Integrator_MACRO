"""Reads the scenario_config.csv produced by the platform.

Format is the one agreed with the platform team (Padroes.md, section 7):

    variable_id,category,variable_name,answer_type,option_id,option_label,numeric_values
    1,General assumptions,NetZero year,option,a,2040.0,
    2,General assumptions,Net emissions caps,slider,,,afolu=10;other=5
    ...
    39,Waste,Wastewater treatment,option,b,Universalization of...,

The stable key is variable_id + option_id. Labels and names are for humans and
for the adjustment report only - never match on them.

Option letters arrive lowercase from the form and are normalized to uppercase
here, because that is how the Macro database writes them (`_25-A`, `B.csv`).
"""

import csv
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILENAME = "scenario_config.csv"
REQUIRED_COLUMNS = ["variable_id", "answer_type"]


@dataclass
class Answer:
    """One line of the form: what the user chose for one variable."""

    variable_id: int
    category: str = ""
    variable_name: str = ""
    answer_type: str = "option"
    option_id: str = ""  # normalized to uppercase: 'A', 'B', 'C', 'D'
    option_label: str = ""
    numeric: dict = field(default_factory=dict)  # sliders: {'afolu': 10.0, 'other': 5.0}

    @property
    def is_slider(self):
        return self.answer_type.strip().lower() == "slider"

    def __str__(self):
        if self.is_slider:
            values = ", ".join(f"{k}={v:g}" for k, v in self.numeric.items())
            return f"{self.variable_id} {self.variable_name} [slider: {values}]"
        return f"{self.variable_id} {self.variable_name} = {self.option_id}) {self.option_label}"


def parse_numeric(text):
    """'afolu=10;other=5' -> {'afolu': 10.0, 'other': 5.0}"""
    values = {}
    for pair in (text or "").split(";"):
        key, _, value = pair.partition("=")
        key = key.strip()
        if not key or not value.strip():
            continue
        try:
            values[key] = float(value.strip().replace(",", "."))
        except ValueError:
            continue
    return values


def _answer(row):
    raw_id = (row.get("variable_id") or "").strip()
    try:
        variable_id = int(float(raw_id))
    except ValueError:
        raise ValueError(f"{CONFIG_FILENAME}: '{raw_id}' is not a valid variable_id")

    return Answer(
        variable_id=variable_id,
        category=(row.get("category") or "").strip(),
        variable_name=(row.get("variable_name") or "").strip(),
        answer_type=(row.get("answer_type") or "option").strip(),
        option_id=(row.get("option_id") or "").strip().upper(),
        option_label=(row.get("option_label") or "").strip(),
        numeric=parse_numeric(row.get("numeric_values")),
    )


def read_scenario_config(source):
    """Accepts a path to the csv, an already parsed list of dicts/Answers, or
    None. Returns a list of Answer, ordered by variable_id.

    A missing file is not an error: it means "run the case as it is", which is
    the individual-test path of the platform.
    """
    if source is None:
        return []
    if isinstance(source, (list, tuple)):
        return sorted(
            [a if isinstance(a, Answer) else _answer(a) for a in source],
            key=lambda a: a.variable_id,
        )

    path = Path(source)
    if path.is_dir():
        path = path / CONFIG_FILENAME
    if not path.is_file():
        return []

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing column(s) {missing}")
        rows = [row for row in reader if (row.get("variable_id") or "").strip()]

    return sorted([_answer(row) for row in rows], key=lambda a: a.variable_id)


def load_catalog(path):
    """Optional: variables_catalog.json, used only to sanity check the answers."""
    import json

    with open(path, encoding="utf-8") as f:
        catalog = json.load(f)
    return {
        str(v["id"]): {str(o["id"]).upper(): o.get("label", "") for o in v.get("options", [])}
        for v in catalog.get("variables", [])
    }


def check_against_catalog(answers, catalog):
    """Returns a list of human readable inconsistencies (never raises)."""
    problems = []
    for answer in answers:
        options = catalog.get(str(answer.variable_id))
        if options is None:
            problems.append(f"variable {answer.variable_id} is not in the catalog")
        elif not answer.is_slider and answer.option_id not in options:
            problems.append(
                f"variable {answer.variable_id}: option '{answer.option_id}' is not in "
                f"the catalog (it has {sorted(options)})"
            )
    return problems
