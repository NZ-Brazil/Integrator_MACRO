"""What a card handler receives, and how it reports back.

A card handler is a function

    def apply(ctx) -> None

registered in cards/__init__.py under the variable_id it answers for. It reads
ctx.answer (the user's choice), edits the case under ctx.case_dir, and records
exactly one adjustment through ctx.applied / ctx.unchanged / ctx.missing /
ctx.not_in_database / ctx.not_implemented.

Rules every handler follows (Padroes.md, section 3):
  - edits the case in place; it does not download or publish anything
  - is idempotent: running it twice with the same option gives the same case
  - never brings the job down over missing data; with strict=False it records a
    warning and the run continues
  - writes nothing when ctx.dry_run is set

Writes are staged, not immediate. ctx.save() holds the edited file in memory and
the orchestrator flushes everything once the handler has returned cleanly; if
the card raises, nothing reaches disk. So a card either applies to all its files
or to none, and "the case kept its own value" in the report is true whenever the
card did not finish - not only when it failed before the first write.
"""

from dataclasses import dataclass, field
from pathlib import Path

from .. import report as R
from ..csvio import DataError, Table, write_table


class CardError(DataError):
    """Raised by a handler when the requested change cannot be made.

    `status` decides how it shows up in the report: key_missing for a file or
    column that is not in the case, not_in_database for data that exists but
    does not cover the option the user picked.
    """

    def __init__(self, message, status=R.KEY_MISSING):
        super().__init__(message)
        self.status = status


@dataclass
class Context:
    case_dir: Path
    answer: object  # scenario_config.Answer
    report: object  # report.Report
    dry_run: bool = False
    strict: bool = False
    options: dict = field(default_factory=dict)  # extra settings from the caller
    pending: dict = field(default_factory=dict)  # path -> staged file, not written yet
    answers: dict = field(default_factory=dict)  # every answer of this run, by variable_id

    def chosen(self, variable_id):
        """The option marked for any variable of this run, or None - including a
        variable Macro has no card for, as long as the platform sent it. Used
        when one card needs to know what a sibling did (card 27 and the costs)
        or, when a variable belongs to another model, to be told what to do by
        it anyway (card 30 and card 6)."""
        other = self.answers.get(variable_id)
        return other.option_id if other else None

    # -- paths -----------------------------------------------------------

    def path(self, *parts):
        return self.case_dir.joinpath(*parts)

    def relative(self, path):
        path = Path(path)
        try:
            return path.relative_to(self.case_dir).as_posix()
        except ValueError:
            return path.as_posix()

    def save(self, target):
        """Stage an edited file. Nothing is written until the card finishes."""
        self.pending[str(target.path)] = target

    def flush(self):
        """Write everything the card staged. Called by the orchestrator."""
        if self.dry_run:
            self.pending.clear()
            return 0
        written = 0
        for target in self.pending.values():
            if isinstance(target, Table):
                write_table(target)
            else:  # a NodeFile
                target.save()
            written += 1
        self.pending.clear()
        return written

    def discard(self):
        """Throw the staged writes away: the card did not finish."""
        self.pending.clear()

    # -- reporting -------------------------------------------------------

    @property
    def option(self):
        return self.answer.option_id

    def applied(self, target, detail=None, frm=None, to=None, changes=None):
        return self.report.add(
            self.answer, R.APPLIED, target=target, frm=frm,
            to=to if to is not None else self._label(), detail=detail, changes=changes,
        )

    def unchanged(self, target, detail=None, changes=None):
        return self.report.add(
            self.answer, R.UNCHANGED, target=target, to=self._label(),
            detail=detail or "the case already carried these values", changes=changes,
        )

    def missing(self, target, detail):
        return self.report.add(self.answer, R.KEY_MISSING, target=target, detail=detail)

    def not_in_database(self, target, detail):
        return self.report.add(self.answer, R.NOT_IN_DATABASE, target=target, detail=detail)

    def not_implemented(self, detail):
        return self.report.add(self.answer, R.NOT_IMPLEMENTED, detail=detail)

    def note(self, message):
        self.report.note(message)

    def log(self, message):
        self.report.log(message)

    def _label(self):
        return f"{self.answer.variable_id}-{self.answer.option_id}"
