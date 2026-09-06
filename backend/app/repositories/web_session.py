"""Shared SQLite session storage; raw session credentials never reach disk."""
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Protocol


class WebSessionStore(Protocol):
    def reserve_attempt(self, client: str, now: float) -> bool: ...
    def create(self, digest: str, csrf: str, credential: str, expires: float, now: float): ...
    def get(self, digest: str): ...
    def delete(self, digest: str): ...


class WebSessionRepository:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS web_sessions (digest TEXT PRIMARY KEY, csrf TEXT NOT NULL, credential TEXT NOT NULL, expires REAL NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS web_login_attempts (client TEXT PRIMARY KEY, attempts INTEGER NOT NULL, expires REAL NOT NULL)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def reserve_attempt(self, client: str, now: float) -> bool:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM web_login_attempts WHERE expires <= ?", (now,))
            row = db.execute("SELECT attempts FROM web_login_attempts WHERE client = ?", (client,)).fetchone()
            if row and row['attempts'] >= 5:
                return False
            db.execute("INSERT INTO web_login_attempts VALUES (?, 1, ?) ON CONFLICT(client) DO UPDATE SET attempts = attempts + 1", (client, now + 300))
            return True

    def create(self, digest: str, csrf: str, credential: str, expires: float, now: float):
        with self.connect() as db:
            db.execute("DELETE FROM web_sessions WHERE expires <= ?", (now,))
            db.execute("INSERT INTO web_sessions VALUES (?, ?, ?, ?)", (digest, csrf, credential, expires))

    def get(self, digest: str):
        with self.connect() as db:
            return db.execute("SELECT * FROM web_sessions WHERE digest = ?", (digest,)).fetchone()

    def delete(self, digest: str):
        with self.connect() as db:
            db.execute("DELETE FROM web_sessions WHERE digest = ?", (digest,))
