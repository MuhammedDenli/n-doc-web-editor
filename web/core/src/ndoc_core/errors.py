"""Exception hierarchy shared by all core modules.

Every error carries a stable machine-readable ``code`` so adapters (FastAPI,
MCP) can map it to HTTP status codes or tool errors without string matching.
"""

from __future__ import annotations


class CoreError(Exception):
    code = "core_error"

    def __init__(self, message: str, **details: object) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message, **self.details}


class PathNotAllowedError(CoreError):
    code = "path_not_allowed"


class FileNotFoundInRepoError(CoreError):
    code = "not_found"


class FileTooLargeError(CoreError):
    code = "file_too_large"


class StaleWriteError(CoreError):
    """The file changed since the caller read it (hash mismatch)."""

    code = "stale_write"


class FileExistsInRepoError(CoreError):
    code = "already_exists"


class InvalidContentError(CoreError):
    code = "invalid_content"


class LockTimeoutError(CoreError):
    code = "lock_timeout"


class UnknownDocumentError(CoreError):
    code = "unknown_document"


class BuildTargetNotAllowedError(CoreError):
    code = "build_target_not_allowed"


class BuildBusyError(CoreError):
    code = "build_busy"


class GitError(CoreError):
    code = "git_error"


class ProtectedBranchError(CoreError):
    code = "protected_branch"


class InvalidBranchNameError(CoreError):
    code = "invalid_branch_name"


class DirtyWorktreeError(CoreError):
    code = "dirty_worktree"
