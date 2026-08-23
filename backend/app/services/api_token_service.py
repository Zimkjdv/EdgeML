from __future__ import annotations

from datetime import datetime, timezone

from app.domain.auth_schemas import ApiTokenCreateRequest, ApiTokenCreateResponse, ApiTokenSummary
from app.repositories.api_token import ApiTokenRecord, ApiTokenRepository


class ApiTokenService:
    def __init__(self, repository: ApiTokenRepository) -> None:
        self._repository = repository

    def create(self, request: ApiTokenCreateRequest) -> ApiTokenCreateResponse:
        if request.expires_at and request.expires_at.astimezone(timezone.utc) <= datetime.now(timezone.utc):
            raise ValueError("Token expiry must be in the future.")
        summary, raw_token = self._repository.create(request.name, request.scopes, request.expires_at)
        return ApiTokenCreateResponse(**summary.model_dump(), token=raw_token)

    def list(self) -> list[ApiTokenSummary]:
        return self._repository.list()

    def revoke(self, token_id: str) -> ApiTokenSummary:
        summary = self._repository.revoke(token_id)
        if summary is None:
            raise KeyError(token_id)
        return summary

    def authenticate(self, token: str) -> ApiTokenRecord | None:
        return self._repository.authenticate(token)

    def has_active_tokens(self) -> bool:
        return self._repository.has_active_tokens()
