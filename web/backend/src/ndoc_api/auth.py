"""Local users, sessions and CSRF protection.

Users and sessions live in SQLite (``Settings.users_db``). Passwords are
Argon2 hashes. A session is a random token in the HttpOnly cookie
``ndoc_session`` (only its SHA-256 is stored). Every state-changing request must
send the session's CSRF token in ``X-CSRF-Token``; the SPA reads it from the
non-HttpOnly cookie ``ndoc_csrf`` (double submit, checked against the session).
"""

from __future__ import annotations

import hashlib
import re
import secrets
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request

from .errors import ApiError

SESSION_COOKIE = "ndoc_session"
CSRF_COOKIE = "ndoc_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
ROLES = ("admin", "editor")

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,31}$")
MIN_PASSWORD = 8
MAX_FAILURES = 5
FAILURE_WINDOW_S = 15 * 60
REFRESH_AFTER_S = 5 * 60

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'editor')),
    disabled INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_sha256 TEXT PRIMARY KEY,
    username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
    csrf TEXT NOT NULL,
    expires_at REAL NOT NULL
);
"""


@dataclass(frozen=True)
class UserRecord:
    username: str
    role: str
    disabled: bool


@dataclass(frozen=True)
class Session:
    user: UserRecord
    csrf: str
    token_sha256: str


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def validate_username(username: str) -> str:
    if not isinstance(username, str) or not USERNAME_RE.match(username):
        raise ApiError(
            422,
            "invalid_value",
            "username: 2-32 characters a-z 0-9 . _ -, starting with a letter or digit",
        )
    return username


def validate_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        raise ApiError(
            422, "invalid_value", f"password must have at least {MIN_PASSWORD} characters"
        )
    return password


def validate_role(role: str) -> str:
    if role not in ROLES:
        raise ApiError(422, "invalid_value", f"role must be one of {', '.join(ROLES)}")
    return role


class UserStore:
    def __init__(self, path: Path, *, session_hours: float = 12.0) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.session_s = session_hours * 3600
        self._hasher = PasswordHasher()
        self._dummy_hash = self._hasher.hash(secrets.token_hex(8))
        self._failures: dict[str, list[float]] = {}
        self._failures_lock = threading.Lock()
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.executescript(_SCHEMA)
        finally:
            db.close()

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except BaseException:
                db.execute("ROLLBACK")
                raise
            db.execute("COMMIT")
        finally:
            db.close()

    # ------------------------------------------------------------- users

    def list_users(self) -> list[UserRecord]:
        with self._db() as db:
            rows = db.execute("SELECT username, role, disabled FROM users ORDER BY username")
            return [UserRecord(u, r, bool(d)) for u, r, d in rows.fetchall()]

    def get_user(self, username: str) -> UserRecord:
        with self._db() as db:
            return self._get(db, username)

    def _get(self, db: sqlite3.Connection, username: str) -> UserRecord:
        row = db.execute(
            "SELECT username, role, disabled FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row is None:
            raise ApiError(404, "not_found", f"user '{username}' does not exist")
        return UserRecord(row[0], row[1], bool(row[2]))

    def has_users(self) -> bool:
        with self._db() as db:
            return db.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def create_user(self, username: str, password: str, role: str = "editor") -> UserRecord:
        validate_username(username)
        validate_password(password)
        validate_role(role)
        pw_hash = self._hasher.hash(password)
        with self._db() as db:
            if db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
                raise ApiError(409, "already_exists", f"user '{username}' already exists")
            db.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?,?,?,?)",
                (username, pw_hash, role, time.time()),
            )
        return UserRecord(username, role, False)

    def update_user(
        self,
        username: str,
        *,
        role: str | None = None,
        password: str | None = None,
        disabled: bool | None = None,
        keep_session: str | None = None,
    ) -> UserRecord:
        """Change role/password/disabled. Password changes and disabling end the
        user's sessions (except ``keep_session``, a token hash)."""
        if role is not None:
            validate_role(role)
        pw_hash = self._hasher.hash(validate_password(password)) if password is not None else None
        with self._db() as db:
            user = self._get(db, username)
            loses_admin = user.role == "admin" and not user.disabled
            loses_admin = loses_admin and (role not in (None, "admin") or disabled is True)
            if loses_admin:
                self._ensure_other_admin(db, username)
            if role is not None:
                db.execute("UPDATE users SET role = ? WHERE username = ?", (role, username))
            if disabled is not None:
                db.execute(
                    "UPDATE users SET disabled = ? WHERE username = ?", (int(disabled), username)
                )
            if pw_hash is not None:
                db.execute(
                    "UPDATE users SET password_hash = ? WHERE username = ?", (pw_hash, username)
                )
            if pw_hash is not None or disabled:
                db.execute(
                    "DELETE FROM sessions WHERE username = ? AND token_sha256 IS NOT ?",
                    (username, keep_session),
                )
            return self._get(db, username)

    def delete_user(self, username: str) -> None:
        with self._db() as db:
            user = self._get(db, username)
            if user.role == "admin" and not user.disabled:
                self._ensure_other_admin(db, username)
            db.execute("DELETE FROM sessions WHERE username = ?", (username,))
            db.execute("DELETE FROM users WHERE username = ?", (username,))

    def _ensure_other_admin(self, db: sqlite3.Connection, username: str) -> None:
        others = db.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin' AND disabled = 0 AND username != ?",
            (username,),
        ).fetchone()[0]
        if not others:
            raise ApiError(409, "last_admin", "the last active admin cannot be removed or demoted")

    # -------------------------------------------------------- passwords

    def verify_password(self, username: str, password: str) -> UserRecord:
        """The user for valid credentials; repeated failures are throttled."""
        self._check_throttle(username)
        with self._db() as db:
            row = db.execute(
                "SELECT username, role, disabled, password_hash FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        stored = row[3] if row else self._dummy_hash  # same work for unknown users
        try:
            self._hasher.verify(stored, password)
            ok = row is not None and not row[2]
        except (VerificationError, InvalidHashError):
            ok = False
        if not ok:
            self._record_failure(username)
            raise ApiError(401, "invalid_credentials", "invalid username or password")
        with self._failures_lock:
            self._failures.pop(username, None)
        if self._hasher.check_needs_rehash(stored):
            with self._db() as db:
                db.execute(
                    "UPDATE users SET password_hash = ? WHERE username = ?",
                    (self._hasher.hash(password), username),
                )
        return UserRecord(row[0], row[1], bool(row[2]))

    def _check_throttle(self, username: str) -> None:
        now = time.time()
        with self._failures_lock:
            recent = [t for t in self._failures.get(username, []) if now - t < FAILURE_WINDOW_S]
            self._failures[username] = recent
            if len(recent) >= MAX_FAILURES:
                retry = int(FAILURE_WINDOW_S - (now - recent[0])) + 1
                raise ApiError(
                    429,
                    "too_many_attempts",
                    "too many failed logins; try again later",
                    retry_after_s=retry,
                )

    def _record_failure(self, username: str) -> None:
        with self._failures_lock:
            self._failures.setdefault(username, []).append(time.time())

    # --------------------------------------------------------- sessions

    def create_session(self, user: UserRecord) -> tuple[str, str]:
        """A new session for ``user``: (token, csrf)."""
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = time.time()
        with self._db() as db:
            db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            db.execute(
                "INSERT INTO sessions (token_sha256, username, csrf, expires_at) VALUES (?,?,?,?)",
                (_sha(token), user.username, csrf, now + self.session_s),
            )
        return token, csrf

    def get_session(self, token: str) -> Session | None:
        """The live session of ``token`` (sliding expiry), or None."""
        now = time.time()
        digest = _sha(token)
        with self._db() as db:
            row = db.execute(
                "SELECT u.username, u.role, u.disabled, s.csrf, s.expires_at "
                "FROM sessions s JOIN users u ON u.username = s.username "
                "WHERE s.token_sha256 = ?",
                (digest,),
            ).fetchone()
            if row is None:
                return None
            if row[4] < now or row[2]:
                db.execute("DELETE FROM sessions WHERE token_sha256 = ?", (digest,))
                return None
            if row[4] - now < self.session_s - REFRESH_AFTER_S:
                db.execute(
                    "UPDATE sessions SET expires_at = ? WHERE token_sha256 = ?",
                    (now + self.session_s, digest),
                )
        return Session(UserRecord(row[0], row[1], False), row[3], digest)

    def delete_session(self, token_sha256: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM sessions WHERE token_sha256 = ?", (token_sha256,))


# ---------------------------------------------------------------- dependencies


def get_store(request: Request) -> UserStore:
    return request.app.state.users


def current_session(request: Request, store: UserStore = Depends(get_store)) -> Session:  # noqa: B008
    token = request.cookies.get(SESSION_COOKIE)
    session = store.get_session(token) if token else None
    if session is None:
        raise ApiError(401, "unauthenticated", "login required")
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not secrets.compare_digest(sent.encode(), session.csrf.encode()):
            raise ApiError(403, "csrf_failed", f"missing or wrong {CSRF_HEADER} header")
    return session


def current_user(session: Session = Depends(current_session)) -> UserRecord:  # noqa: B008
    return session.user


def require_editor(user: UserRecord = Depends(current_user)) -> UserRecord:  # noqa: B008
    if user.role not in ("admin", "editor"):
        raise ApiError(403, "forbidden", "editor role required")
    return user


def require_admin(user: UserRecord = Depends(current_user)) -> UserRecord:  # noqa: B008
    if user.role != "admin":
        raise ApiError(403, "forbidden", "admin role required")
    return user
