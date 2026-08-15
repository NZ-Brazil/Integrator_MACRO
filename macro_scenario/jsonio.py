"""Editing the node files without reformatting them.

system/nodes_<period>.json is hand maintained and its indentation is not
uniform - part of the file is indented with 4 spaces, part with 2. Loading it
with json and dumping it back rewrites about a thousand lines that nobody
touched, which buries the one number that actually changed.

So the edits here are textual and anchored on the node id: find the instance
block for an id, find the section inside it (constraints, rhs_policy), replace
the literal after the key. Every write is parsed with json afterwards, so a
malformed result is caught before it reaches the case.
"""

import json
import re
from pathlib import Path

from .csvio import DataError

NUMBER_OR_LITERAL = r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?|true|false|null"


class NodeFile:
    """One nodes_<period>.json, edited as text and validated as json."""

    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_file():
            raise DataError(f"{self.path} not found")
        self.text = self.path.read_text(encoding="utf-8")
        self.original = self.text
        self.data = json.loads(self.text)  # fails early on a broken file

    @property
    def changed(self):
        return self.text != self.original

    # -- locating --------------------------------------------------------

    def block(self, node_id):
        """The slice of text holding one instance, from its id to the next id."""
        anchor = f'"id": "{node_id}"'
        start = self.text.find(anchor)
        if start < 0:
            raise DataError(f"{self.path.name}: no node with id '{node_id}'")
        if self.text.find(anchor, start + 1) >= 0:
            raise DataError(f"{self.path.name}: id '{node_id}' appears more than once")
        end = self.text.find('"id":', start + len(anchor))
        return start, end if end > 0 else len(self.text)

    def _match(self, node_id, key, section=None):
        start, end = self.block(node_id)
        offset = start
        if section is not None:
            found = self.text.find(f'"{section}"', start, end)
            if found < 0:
                raise DataError(f"{self.path.name}: node '{node_id}' has no '{section}'")
            offset = found
        pattern = re.compile(rf'("{re.escape(key)}"\s*:\s*)({NUMBER_OR_LITERAL})')
        match = pattern.search(self.text, offset, end)
        if match is None:
            where = f" inside '{section}'" if section else ""
            raise DataError(f"{self.path.name}: node '{node_id}' has no '{key}'{where}")
        return match

    # -- reading and writing ---------------------------------------------

    def get(self, node_id, key, section=None):
        return self._match(node_id, key, section).group(2)

    def set(self, node_id, key, value, section=None):
        """Replace one scalar. Returns (before, after); after == before means
        nothing was written."""
        match = self._match(node_id, key, section)
        before = match.group(2)
        after = self.literal(value)
        if before == after:
            return before, after
        self.text = self.text[: match.start(2)] + after + self.text[match.end(2):]
        return before, after

    def set_list(self, node_id, key, value):
        """Replace a one-element list such as "max_supply": [ 72478.43 ]."""
        start, end = self.block(node_id)
        pattern = re.compile(rf'("{re.escape(key)}"\s*:\s*\[\s*)({NUMBER_OR_LITERAL})(\s*\])')
        match = pattern.search(self.text, start, end)
        if match is None:
            raise DataError(f"{self.path.name}: node '{node_id}' has no single valued '{key}'")
        before = match.group(2)
        after = self.literal(value)
        if before != after:
            self.text = self.text[: match.start(2)] + after + self.text[match.end(2):]
        return before, after

    @staticmethod
    def literal(value):
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return "null"
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return repr(value) if isinstance(value, float) else str(value)

    def save(self, dry_run=False):
        if not self.changed:
            return False
        json.loads(self.text)  # never leave a broken node file behind
        if not dry_run:
            self.path.write_text(self.text, encoding="utf-8")
        return True

    def write(self):
        return self.save()
