"""The adjustment report (Padroes.md, section 5).

Every run produces one report, published by the worker at
jobs/{job_id}/macro-energy/adjustments.json and shown behind "View adjustments".
Its job is to make sure no automatic change to the case is invisible to whoever
reads the results.

One adjustment record per variable consumed by Macro. Cards that touch many
files (25 rewrites 192 asset files) keep the per-file breakdown in `changes`,
so the record stays readable while the detail is still there.
"""

import json
from datetime import datetime, timezone

MODEL = "macro-energy"

APPLIED = "applied"
UNCHANGED = "unchanged"
NOT_IN_DATABASE = "not_in_database"
KEY_MISSING = "key_missing"
NOT_IMPLEMENTED = "not_implemented"

WARNING_STATUSES = {NOT_IN_DATABASE, KEY_MISSING}
STATUSES = {APPLIED, UNCHANGED, NOT_IN_DATABASE, KEY_MISSING, NOT_IMPLEMENTED}


class Report:
    def __init__(self, job_id, logger=print):
        self.job_id = job_id
        self.logger = logger or (lambda message: None)
        self.adjustments = []
        self.steps = []
        self.warnings = []
        self.notes = []
        self.targets = []
        self.variables_received = 0
        self.failed = False

    # -- recording -------------------------------------------------------

    def add(self, answer, status, target=None, frm=None, to=None, detail=None, changes=None):
        if status not in STATUSES:
            raise ValueError(f"unknown status: {status}")

        record = {
            "variable_id": str(answer.variable_id),
            "variable_name": answer.variable_name,
            "option_id": answer.option_id,
            "option_label": answer.option_label,
            "target": target,
            "from": frm,
            "to": to,
            "status": status,
            "detail": detail,
        }
        if changes:
            record["changes"] = changes
        self.adjustments.append(record)

        if target and target not in self.targets:
            self.targets.append(target)
        if status in WARNING_STATUSES:
            message = f"[{answer.variable_id}] {answer.variable_name}: {detail or status}"
            self.warnings.append(message)

        self.log(f"  {status:16s} {answer} -> {detail or target or ''}")
        return record

    def step(self, name, detail, **extra):
        """A pipeline step that is not a form variable: the EP2MACRO import, the TDR.

        Kept apart from `adjustments`, which the platform reads as one entry per
        form variable, but still in the report so nothing is invisible."""
        record = {"step": name, "detail": detail, **extra}
        self.steps.append(record)
        self.log(f"  step             {name}: {detail}")
        return record

    def note(self, message):
        self.notes.append(message)

    def warn(self, message):
        self.warnings.append(message)
        self.log(f"  warning          {message}")

    def log(self, message):
        self.logger(message)

    # -- output ----------------------------------------------------------

    def counts(self):
        counted = {status: 0 for status in STATUSES}
        for record in self.adjustments:
            counted[record["status"]] += 1
        return counted

    def status(self):
        if self.failed:
            return "failed"
        if not self.adjustments and not self.steps and not self.warnings:
            return "skipped"
        if self.warnings:
            return "applied_with_warnings"
        return "applied"

    def to_dict(self):
        counted = self.counts()
        return {
            "job_id": self.job_id,
            "model": MODEL,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": self.status(),
            "target": ", ".join(self.targets),
            "summary": {
                "applied": counted[APPLIED],
                "unchanged": counted[UNCHANGED],
                "warnings": len(self.warnings),
                "not_implemented": counted[NOT_IMPLEMENTED],
                "variables_received": self.variables_received,
            },
            "adjustments": self.adjustments,
            "steps": self.steps,
            "warnings": self.warnings,
            "notes": self.notes,
        }

    def write(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
            f.write("\n")
        return path
