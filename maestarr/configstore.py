"""Settings, users and sessions in SQLite — everything the UI can change.

Environment variables are only the starting point: any setting saved from the
UI (onboarding or the Settings page) is stored here and wins. Bootstrap values
that must be known before the database can be opened (data dir, host, port,
log level) stay environment-only.

Uses the standard library `sqlite3` on purpose: settings are read
synchronously at startup and are tiny. Conversations live in the same file
but go through `aiosqlite` (see `store.py`).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at REAL NOT NULL
);
"""

# Settings that may never be changed from the UI (they decide where the UI
# and the database themselves live).
BOOTSTRAP_ONLY = {
    "MAESTARR_ALLOW_ADULT",  # an admin's lock: set in the environment, never from the UI
    "MAESTARR_HOST",
    "MAESTARR_PORT",
    "MAESTARR_DATA_DIR",
    "MAESTARR_LOG_DIR",
    "MAESTARR_LOG_LEVEL",
}

SESSION_TTL = 30 * 24 * 3600

_lock = threading.Lock()


class ConfigStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as db:
            # Write-ahead logging: readers (session checks) never wait for a writer.
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        with _lock:
            db = sqlite3.connect(self.path, timeout=30)
            db.execute("PRAGMA foreign_keys = ON")
            try:
                yield db
                db.commit()
            finally:
                db.close()

    # --- settings -------------------------------------------------------------

    def values(self) -> dict[str, Any]:
        with self._conn() as db:
            rows = db.execute("SELECT key, value FROM config").fetchall()
        return {k: json.loads(v) for k, v in rows}

    def get(self, key: str, default: Any = None) -> Any:
        with self._conn() as db:
            row = db.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def update(self, values: dict[str, Any]) -> None:
        """Save settings; `None` deletes a key (falls back to env/default)."""
        bad = BOOTSTRAP_ONLY & set(values)
        if bad:
            raise ValueError(f"cannot change {', '.join(sorted(bad))} at runtime")
        now = time.time()
        with self._conn() as db:
            for key, value in values.items():
                if value is None:
                    db.execute("DELETE FROM config WHERE key = ?", (key,))
                else:
                    db.execute(
                        "INSERT INTO config (key, value, updated_at) VALUES (?, ?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                        (key, json.dumps(value), now),
                    )

    # --- users -----------------------------------------------------------------

    def has_users(self) -> bool:
        with self._conn() as db:
            return db.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def create_user(self, username: str, password: str) -> int:
        if len(password) < 8:
            raise ValueError("password must be at least 8 characters")
        if not username.strip():
            raise ValueError("username is required")
        with self._conn() as db:
            cur = db.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username.strip(), hash_password(password), time.time()),
            )
            return int(cur.lastrowid or 0)

    def verify_user(self, username: str, password: str) -> Optional[dict[str, Any]]:
        with self._conn() as db:
            row = db.execute(
                "SELECT id, username, password_hash FROM users WHERE username = ?", (username.strip(),)
            ).fetchone()
        if row and verify_password(password, row[2]):
            return {"id": row[0], "username": row[1]}
        verify_password(password, _DUMMY_HASH)  # equal work for unknown users
        return None

    def set_password(self, user_id: int, password: str) -> None:
        if len(password) < 8:
            raise ValueError("password must be at least 8 characters")
        with self._conn() as db:
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), user_id))
            db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    # --- sessions --------------------------------------------------------------

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        with self._conn() as db:
            db.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
            db.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (_sha(token), user_id, time.time() + SESSION_TTL),
            )
        return token

    def session_user(self, token: str) -> Optional[dict[str, Any]]:
        if not token:
            return None
        with self._conn() as db:
            row = db.execute(
                "SELECT u.id, u.username FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash = ? AND s.expires_at > ?",
                (_sha(token), time.time()),
            ).fetchone()
        return {"id": row[0], "username": row[1]} if row else None

    def delete_session(self, token: str) -> None:
        with self._conn() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (_sha(token),))


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str) -> str:
    """scrypt (stdlib) with a random salt, encoded as `scrypt$n$r$p$salt$hash`.

    >>> h = hash_password("correct horse")
    >>> verify_password("correct horse", h), verify_password("wrong", h)
    (True, False)
    """
    salt = os.urandom(16)
    n, r, p = 2**14, 8, 1
    digest = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)
    return f"scrypt${n}${r}${p}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, n, r, p, salt, digest = encoded.split("$")
        candidate = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate.hex(), digest)


_DUMMY_HASH = hash_password("timing-equaliser")
