"""Error responses: ``{code, message, details}`` with a status per core error code."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ndoc_core import CoreError

from .models import ErrorBody

STATUS_BY_CODE: dict[str, int] = {
    "path_not_allowed": 403,
    "protected_branch": 403,
    "not_found": 404,
    "unknown_document": 404,
    "unknown_table": 404,
    "row_not_found": 404,
    "stale_write": 409,
    "already_exists": 409,
    "duplicate_key": 409,
    "row_referenced": 409,
    "build_busy": 409,
    "lock_timeout": 409,
    "dirty_worktree": 409,
    "file_too_large": 413,
    "invalid_content": 422,
    "invalid_pattern": 422,
    "invalid_value": 422,
    "invalid_branch_name": 422,
    "foreign_key_violation": 422,
    "text_not_found": 422,
    "ambiguous_match": 422,
    "build_target_not_allowed": 422,
    "tool_missing": 503,
}


class ApiError(Exception):
    """An error raised by the adapter itself (auth, users)."""

    def __init__(self, status: int, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return ErrorBody(code=code, message=message, details=details or {}).model_dump(mode="json")


def core_error_body(exc: CoreError) -> dict[str, Any]:
    return error_body(exc.code, exc.message, {k: v for k, v in exc.details.items()})


def _json(status: int, body: dict[str, Any], headers: dict[str, str] | None = None):
    return JSONResponse(status_code=status, content=body, headers=headers)


def install(app: FastAPI) -> None:
    @app.exception_handler(CoreError)
    async def _core(_: Request, exc: CoreError):
        return _json(STATUS_BY_CODE.get(exc.code, 500), core_error_body(exc))

    @app.exception_handler(ApiError)
    async def _api(_: Request, exc: ApiError):
        return _json(exc.status, error_body(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        errors = [
            {"loc": [str(p) for p in e.get("loc", ())], "msg": e.get("msg", "")}
            for e in exc.errors()
        ]
        return _json(422, error_body("invalid_request", "invalid request", {"errors": errors}))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _json(exc.status_code, error_body(code, str(exc.detail)), exc.headers)


def responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI error responses (all share :class:`ErrorBody`)."""
    return {s: {"model": ErrorBody} for s in statuses}
