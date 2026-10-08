"""Run n-doc builds in the ``ndesign/n-doc`` container (same as ``runmake.sh``).

Only allow-listed make targets run, one build at a time per repository, with a
timeout that also kills the container. The full log goes to the state dir; the
result carries its tail, extracted error lines and the PDFs that were updated.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import docs
from .errors import BuildBusyError, BuildTargetNotAllowedError, CoreError
from .repo import Repo

WORKFLOW_FILE = ".github/workflows/build_n-doc_template.yml"
IMAGE = "ndesign/n-doc"
DEFAULT_TIMEOUT = 30 * 60
TAIL_LINES = 80
BUILD_LOCK = "build"

# make alias -> Makefile variable holding the directories it builds
ALIASES: dict[str, str] = {
    "st": "ST_DIR",
    "fsp": "FSP_DIR",
    "tds": "TDS_DIR",
    "arc": "ARC_DIR",
    "ate": "ATE_DIR",
    "ref": "REF_DIR",
    "mwe": "MWE_DIRS",
    "all": "PDF_DIRS",
    "delivery": "PDF_DIRS",
}
UTILITY_TARGETS = frozenset({"db", "clean", "cleanmwe", "hooks"})

_VERSION_RE = re.compile(r"container:\s*ndesign/n-doc:([0-9A-Za-z._-]+)")
_ERROR_RE = re.compile(r"^(! .*|.*:\d+: .*|make(\[\d+\])?: \*\*\* .*|.*\bis undefined\b.*)$")

OutputCallback = Callable[[str], None]


@dataclass
class BuildResult:
    target: str
    ok: bool
    returncode: int
    duration_s: float
    timed_out: bool
    log_file: str
    log_tail: str
    errors: list[str] = field(default_factory=list)
    pdfs: list[str] = field(default_factory=list)


def allowed_targets(repo: Repo) -> list[str]:
    names = [d.name for d in docs.list_documents(repo)]
    return sorted(set(ALIASES) | UTILITY_TARGETS | set(names))


def target_dirs(repo: Repo, target: str) -> list[str]:
    """Document directories whose PDFs a target produces."""
    variables = docs.makefile_vars(repo)
    if target in ALIASES:
        return variables.get(ALIASES[target], "").split()
    if target in {d.name for d in docs.list_documents(repo)}:
        return [target]
    return []


def validate_target(repo: Repo, target: str) -> str:
    if not isinstance(target, str) or target not in allowed_targets(repo):
        raise BuildTargetNotAllowedError(
            f"build target '{target}' is not allowed", target=target, allowed=allowed_targets(repo)
        )
    return target


def engine_version(repo: Repo) -> str:
    override = os.environ.get("NDOC_ENGINE_VERSION")
    if override:
        if not re.fullmatch(r"[0-9A-Za-z._-]+", override):
            raise CoreError("invalid NDOC_ENGINE_VERSION")
        return override
    workflow = repo.root / WORKFLOW_FILE
    m = _VERSION_RE.search(workflow.read_text(encoding="utf-8")) if workflow.is_file() else None
    if not m:
        raise CoreError(f"cannot determine n-doc engine version from {WORKFLOW_FILE}")
    return m.group(1)


def docker_command(repo: Repo, target: str, *, container: str, jobs: int = 4) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        container,
        "--volume",
        f"{repo.docker_root}:/data",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        f"{IMAGE}:{engine_version(repo)}",
        "make",
        f"-j{int(jobs)}",
        target,
    ]


def build(
    repo: Repo,
    target: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    jobs: int = 4,
    on_output: OutputCallback | None = None,
) -> BuildResult:
    """Run ``make <target>`` in the container. Raises BuildBusyError if one runs."""
    validate_target(repo, target)
    with repo.try_lock(BUILD_LOCK) as acquired:
        if not acquired:
            raise BuildBusyError("another build is running")
        return _build_locked(repo, target, timeout=timeout, jobs=jobs, on_output=on_output)


def _build_locked(
    repo: Repo, target: str, *, timeout: float, jobs: int, on_output: OutputCallback | None
) -> BuildResult:
    log_dir = Path(repo.state_dir) / "builds"
    log_dir.mkdir(parents=True, exist_ok=True)
    build_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    log_path = log_dir / f"{build_id}-{target}.log"
    started = time.time()
    tail: deque[str] = deque(maxlen=TAIL_LINES)
    errors: list[str] = []

    steps = [target]
    if target != "hooks" and _needs_hooks(repo):
        steps.insert(0, "hooks")

    returncode, timed_out = 0, False
    with log_path.open("w", encoding="utf-8") as log:
        for step in steps:
            deadline = started + timeout
            returncode, timed_out = _run_container(
                repo,
                step,
                jobs,
                deadline,
                log,
                tail,
                errors,
                on_output,
            )
            if returncode != 0:
                break

    pdfs = [
        f"{d}/{d}.pdf"
        for d in target_dirs(repo, target)
        if (p := repo.root / d / f"{d}.pdf").is_file() and p.stat().st_mtime >= started - 1
    ]
    return BuildResult(
        target=target,
        ok=returncode == 0 and not timed_out,
        returncode=returncode,
        duration_s=round(time.time() - started, 1),
        timed_out=timed_out,
        log_file=str(log_path),
        log_tail="\n".join(tail),
        errors=errors[:50],
        pdfs=pdfs,
    )


def _needs_hooks(repo: Repo) -> bool:
    git_dir = repo.root / ".git"
    return git_dir.is_dir() and not (git_dir / "gitHeadInfo.gin").is_file()


def _run_container(
    repo: Repo,
    target: str,
    jobs: int,
    deadline: float,
    log,
    tail: deque[str],
    errors: list[str],
    on_output: OutputCallback | None,
) -> tuple[int, bool]:
    container = f"ndoc-build-{uuid.uuid4().hex[:12]}"
    cmd = docker_command(repo, target, container=container, jobs=jobs)
    log.write(f"$ {' '.join(cmd)}\n")
    proc = subprocess.Popen(
        cmd,
        cwd=repo.root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    timed_out = threading.Event()

    def watchdog() -> None:
        if _wait_until(proc, deadline):
            timed_out.set()
            subprocess.run(["docker", "kill", container], capture_output=True, check=False)
            proc.kill()

    watcher = threading.Thread(target=watchdog, daemon=True)
    watcher.start()

    for raw in proc.stdout or ():
        line = raw.rstrip("\n")
        log.write(raw)
        tail.append(line)
        if _ERROR_RE.match(line) and line not in errors:
            errors.append(line)
        if on_output:
            on_output(line)
    proc.wait()
    watcher.join(timeout=5)
    if timed_out.is_set():
        log.write("\n*** build timed out, container killed ***\n")
        tail.append("*** build timed out, container killed ***")
    return proc.returncode, timed_out.is_set()


def _wait_until(proc: subprocess.Popen, deadline: float) -> bool:
    """Wait for the process; True if the deadline passed while it still ran."""
    try:
        proc.wait(timeout=max(0.0, deadline - time.time()))
        return False
    except subprocess.TimeoutExpired:
        return True
