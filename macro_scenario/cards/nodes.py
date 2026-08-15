"""Shared helpers for the cards that edit system/nodes_<period>.json."""

import re
from pathlib import Path

from ..csvio import DataError
from ..jsonio import NodeFile

NODES_DIR = "system"
NODES_PATTERN = "nodes_*.json"
PERIOD_IN_NAME = re.compile(r"nodes_(\d{4})\.json$", re.IGNORECASE)


def node_paths(case_dir):
    """[(2025, Path), (2030, Path), ...] for every period file in the case."""
    folder = Path(case_dir) / NODES_DIR
    found = []
    for path in sorted(folder.glob(NODES_PATTERN)):
        match = PERIOD_IN_NAME.search(path.name)
        if match:
            found.append((int(match.group(1)), path))
    if not found:
        raise DataError(f"no {NODES_DIR}/{NODES_PATTERN} in the case")
    return found


def open_nodes(ctx):
    """[(period, NodeFile), ...]"""
    return [(period, NodeFile(path)) for period, path in node_paths(ctx.case_dir)]
