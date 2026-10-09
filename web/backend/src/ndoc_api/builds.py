"""Background builds: one at a time, status and live log tail for polling."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from ndoc_core import CoreError, Repo, build, checks
from ndoc_core.build import BUILD_LOCK, TAIL_LINES
from ndoc_core.errors import BuildBusyError

from .deps import report
from .errors import core_error_body


class BuildManager:
    """Runs ``ndoc_core.build.build`` in a thread and keeps the latest status.

    The core build lock is inter-process, so a build started meanwhile through
    MCP is reported as busy too (before starting when possible, otherwise as a
    failed build with error code ``build_busy``).
    """

    def __init__(self, repo: Repo) -> None:
        self.repo = repo
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._status: dict[str, Any] = {"state": "idle"}
        self._tail: deque[str] = deque(maxlen=TAIL_LINES)

    def status(self) -> dict[str, Any]:
        with self._lock:
            out = dict(self._status)
            if out["state"] == "running":
                out["log_tail"] = list(self._tail)
                out["elapsed_s"] = round(time.time() - out["started_at"], 1)
            return out

    def start(self, target: str) -> dict[str, Any]:
        build.validate_target(self.repo, target)
        with self._lock:
            if self._status["state"] == "running":
                raise BuildBusyError("another build is running", target=self._status["target"])
            with self.repo.try_lock(BUILD_LOCK) as free:
                if not free:
                    raise BuildBusyError("another build is running (outside the web server)")
            self._tail.clear()
            self._status = {"state": "running", "target": target, "started_at": time.time()}
            self._thread = threading.Thread(
                target=self._run, args=(target,), name=f"ndoc-build-{target}", daemon=True
            )
            self._thread.start()
        return self.status()

    def wait(self, timeout: float | None = None) -> None:
        """Wait for the current build (tests, shutdown)."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _on_output(self, line: str) -> None:
        with self._lock:
            self._tail.append(line.rstrip("\n"))

    def _run(self, target: str) -> None:
        started = self._status["started_at"]
        final: dict[str, Any]
        try:
            result = build.build(self.repo, target, on_output=self._on_output)
            final = {
                "state": "succeeded" if result.ok else "failed",
                "returncode": result.returncode,
                "timed_out": result.timed_out,
                "elapsed_s": result.duration_s,
                "log_tail": result.log_tail.splitlines(),
                "errors": result.errors,
                "pdfs": result.pdfs,
            }
            if result.pdfs:
                final["pdf_checks"] = report(checks.check_pdf_sanity(self.repo, result.pdfs))
        except CoreError as exc:
            final = {"state": "failed", "error": core_error_body(exc)}
        except Exception as exc:  # noqa: BLE001 - reported to the client, not swallowed
            final = {
                "state": "failed",
                "error": {"code": "internal_error", "message": str(exc), "details": {}},
            }
        with self._lock:
            final.setdefault("log_tail", list(self._tail))
            final.setdefault("elapsed_s", round(time.time() - started, 1))
            self._status = {"target": target, "started_at": started, **final}
