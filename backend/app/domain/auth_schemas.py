from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


TokenScope = Literal["api", "tokens:manage"]


class ApiTokenCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: list[TokenScope] = Field(default_factory=lambda: ["api"], min_length=1, max_length=4)
    expires_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("scopes")
    @classmethod
    def normalize_scopes(cls, value: list[TokenScope]) -> list[TokenScope]:
        return list(dict.fromkeys(value))

    @field_validator("expires_at")
    @classmethod
    def normalize_expiry(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        # Treat values without an explicit offset as UTC so API clients do not
        # accidentally create tokens that expire in the server's local timezone.
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class ApiTokenSummary(BaseModel):
    id: str
    name: str
    token_prefix: str
    scopes: list[TokenScope]
    created_at: datetime
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    status: Literal["active", "expired", "revoked"]


class ApiTokenCreateResponse(ApiTokenSummary):
    token: str
