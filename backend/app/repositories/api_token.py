from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
from typing import Protocol
from uuid import uuid4

from app.domain.auth_schemas import ApiTokenSummary, TokenScope


@dataclass(frozen=True)
class ApiTokenRecord:
    summary: ApiTokenSummary
    token_hash: str

    @property
    def scopes(self) -> list[TokenScope]:
        return self.summary.scopes


class ApiTokenRepository(Protocol):
    def has_active_tokens(self) -> bool:
        ...

    def create(self, name: str, scopes: list[TokenScope], expires_at: datetime | None) -> tuple[ApiTokenSummary, str]:
        ...

    def list(self) -> list[ApiTokenSummary]:
        ...

    def revoke(self, token_id: str) -> ApiTokenSummary | None:
        ...

    def authenticate(self, token: str) -> ApiTokenRecord | None:
        ...


class SqliteApiTokenRepository:
    """SQLite-backed token metadata store; raw token values are never persisted."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def has_active_tokens(self) -> bool:
        now = _now().isoformat()
        with self._connect() as connection:
            row = connection.execute(
                """SELECT 1 FROM api_tokens
                   WHERE revoked_at IS NULL AND (expires_at IS NULL OR expires_at > ?)
                   LIMIT 1""",
                (now,),
            ).fetchone()
        return row is not None

    def create(self, name: str, scopes: list[TokenScope], expires_at: datetime | None) -> tuple[ApiTokenSummary, str]:
        raw_token = f"edg_{secrets.token_urlsafe(32)}"
        token_id = str(uuid4())
        created_at = _now()
        prefix = raw_token[:12]
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO api_tokens
                   (id, name, token_prefix, token_hash, scopes, created_at, expires_at, last_used_at, revoked_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)""",
                (
                    token_id,
                    name,
                    prefix,
                    _hash_token(raw_token),
                    json.dumps(scopes),
                    created_at.isoformat(),
                    _serialize_datetime(expires_at),
                ),
            )
        return self._summary_from_values(token_id, name, prefix, scopes, created_at, expires_at, None, None), raw_token

    def list(self) -> list[ApiTokenSummary]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM api_tokens ORDER BY created_at DESC").fetchall()
        return [self._summary_from_row(row) for row in rows]

    def revoke(self, token_id: str) -> ApiTokenSummary | None:
        revoked_at = _now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE api_tokens SET revoked_at = COALESCE(revoked_at, ?) WHERE id = ?",
                (revoked_at.isoformat(), token_id),
            )
            row = connection.execute("SELECT * FROM api_tokens WHERE id = ?", (token_id,)).fetchone()
        return self._summary_from_row(row) if row else None

    def authenticate(self, token: str) -> ApiTokenRecord | None:
        token_hash = _hash_token(token)
        now = _now()
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM api_tokens WHERE token_hash = ?", (token_hash,)).fetchone()
            if row is None or row["revoked_at"] is not None:
                return None
            expires_at = _parse_datetime(row["expires_at"])
            if expires_at and expires_at <= now:
                return None
            connection.execute("UPDATE api_tokens SET last_used_at = ? WHERE id = ?", (now.isoformat(), row["id"]))
            row = dict(row)
            row["last_used_at"] = now.isoformat()
        return ApiTokenRecord(self._summary_from_row(row), token_hash)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS api_tokens (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    token_prefix TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    scopes TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    last_used_at TEXT,
                    revoked_at TEXT
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    @classmethod
    def _summary_from_row(cls, row: sqlite3.Row | dict) -> ApiTokenSummary:
        scopes = json.loads(row["scopes"])
        return cls._summary_from_values(
            row["id"], row["name"], row["token_prefix"], scopes,
            _parse_datetime(row["created_at"]), _parse_datetime(row["expires_at"]),
            _parse_datetime(row["last_used_at"]), _parse_datetime(row["revoked_at"]),
        )

    @staticmethod
    def _summary_from_values(
        token_id: str,
        name: str,
        prefix: str,
        scopes: list[TokenScope],
        created_at: datetime,
        expires_at: datetime | None,
        last_used_at: datetime | None,
        revoked_at: datetime | None,
    ) -> ApiTokenSummary:
        now = _now()
        status = "revoked" if revoked_at else "expired" if expires_at and expires_at <= now else "active"
        return ApiTokenSummary(
            id=token_id, name=name, token_prefix=prefix, scopes=scopes,
            created_at=created_at, expires_at=expires_at, last_used_at=last_used_at,
            revoked_at=revoked_at, status=status,
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _serialize_datetime(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(timezone.utc)
