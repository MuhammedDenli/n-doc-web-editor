"""ndoc_core: the single source of truth for the n-doc web/agent layer.

Modules: ``files`` (path guard, read/write), ``docs`` (documents, \\input tree),
``build`` (containerized make), ``checks`` (LaTeX + reference + CSV checks),
``csvdata`` (CSV schema, row edits, key validation),
``git`` (non-destructive Git). All take a :class:`Repo` as first argument.
"""

from .errors import CoreError
from .repo import Repo

__all__ = ["CoreError", "Repo"]
