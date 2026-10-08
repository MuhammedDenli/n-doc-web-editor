"""Small LaTeX text helpers shared by docs and checks."""

from __future__ import annotations

import re

_COMMENT_RE = re.compile(r"(?<!\\)((?:\\\\)*)%.*$", re.MULTILINE)


def strip_comments(text: str) -> str:
    """Blank out ``%`` comments with spaces, so offsets stay valid (``\\%`` is kept)."""
    return _COMMENT_RE.sub(lambda m: m.group(1) + " " * (len(m.group(0)) - len(m.group(1))), text)


def line_col(text: str, offset: int) -> tuple[int, int]:
    """1-based line and column of ``offset``."""
    line = text.count("\n", 0, offset) + 1
    col = offset - (text.rfind("\n", 0, offset) + 1) + 1
    return line, col
