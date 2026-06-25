"""Diff parsing utilities for the Review Council.

Handles unified diff format — extracts hunks, file paths, and
maps line numbers so reviews can reference specific locations.
"""

import re
from typing import List, Dict, Optional


# ── Types ───────────────────────────────────────────────────────────

class Hunk:
    """A single hunk from a unified diff."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: List[str]

    def __init__(self, header: str, lines: List[str]):
        m = re.match(
            r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@",
            header,
        )
        self.old_start = int(m.group(1)) if m else 0
        self.old_count = int(m.group(2)) if m and m.group(2) else 1
        self.new_start = int(m.group(3)) if m else 0
        self.new_count = int(m.group(4)) if m and m.group(4) else 1
        self.lines = lines

    def __repr__(self) -> str:
        return (
            f"Hunk(@@ -{self.old_start},{self.old_count} "
            f"+{self.new_start},{self.new_count} @@, "
            f"{len(self.lines)} lines)"
        )


class DiffFile:
    """A single file's changes in a diff."""
    old_path: str
    new_path: str
    hunks: List[Hunk]

    def __init__(self, old_path: str, new_path: str, hunks: List[Hunk]):
        self.old_path = old_path
        self.new_path = new_path
        self.hunks = hunks

    @property
    def path(self) -> str:
        """Display path (prefers new path for renamed files)."""
        return self.new_path if self.new_path != "/dev/null" else self.old_path

    def __repr__(self) -> str:
        return f"DiffFile({self.path}, {len(self.hunks)} hunks)"


# ── Parsing ─────────────────────────────────────────────────────────

def parse_diff(diff_text: str) -> List[DiffFile]:
    """Parse a unified diff string into structured ``DiffFile`` objects.

    Args:
        diff_text: Raw unified diff output (e.g. from ``git diff``).

    Returns:
        Ordered list of changed files.
    """
    files: List[DiffFile] = []
    current_old = ""
    current_new = ""
    current_hunks: List[Hunk] = []
    current_hunk_lines: List[str] = []
    current_hunk_header = ""

    def _flush_hunk():
        if current_hunk_header and current_hunk_lines:
            current_hunks.append(Hunk(current_hunk_header, current_hunk_lines))

    def _flush_file():
        _flush_hunk()
        if current_old or current_new:
            files.append(DiffFile(current_old, current_new, current_hunks))

    for line in diff_text.splitlines(keepends=True):
        stripped = line.rstrip("\n\r")

        # File headers: --- a/...  or  +++ b/...
        if stripped.startswith("--- "):
            _flush_file()
            current_old = stripped[4:].lstrip("a/")
            current_hunks = []
            current_hunk_header = ""
            current_hunk_lines = []
        elif stripped.startswith("+++ "):
            current_new = stripped[4:].lstrip("b/")
        # Hunk header
        elif stripped.startswith("@@"):
            _flush_hunk()
            current_hunk_header = stripped
            current_hunk_lines = []
        elif stripped.startswith("diff --git"):
            _flush_file()
            current_old = ""
            current_new = ""
            current_hunks = []
            current_hunk_header = ""
            current_hunk_lines = []
        elif current_hunk_header is not None:
            current_hunk_lines.append(line)

    _flush_file()
    return files


# ── Summary stats ──────────────────────────────────────────────────

def diff_summary(diff_text: str) -> str:
    """Return a human-readable one-line summary of a diff."""
    files = parse_diff(diff_text)
    added = sum(
        1 for f in files for h in f.hunks for l in h.lines if l.startswith("+")
    )
    removed = sum(
        1 for f in files for h in f.hunks for l in h.lines if l.startswith("-")
    )
    file_count = len(files)
    return f"{file_count} file(s), +{added}/-{removed} lines"
