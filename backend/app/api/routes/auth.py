from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_api_token_service, require_token_management
from app.domain.auth_schemas import ApiTokenCreateRequest, ApiTokenCreateResponse, ApiTokenSummary
from app.services.api_token_service import ApiTokenService


router = APIRouter(prefix="/auth/tokens", dependencies=[Depends(require_token_management)])


@router.post("", response_model=ApiTokenCreateResponse, status_code=status.HTTP_201_CREATED)
def create_token(
    request: ApiTokenCreateRequest,
    service: ApiTokenService = Depends(get_api_token_service),
) -> ApiTokenCreateResponse:
    try:
        return service.create(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=list[ApiTokenSummary])
def list_tokens(service: ApiTokenService = Depends(get_api_token_service)) -> list[ApiTokenSummary]:
    return service.list()


@router.delete("/{token_id}", response_model=ApiTokenSummary)
def revoke_token(token_id: str, service: ApiTokenService = Depends(get_api_token_service)) -> ApiTokenSummary:
    try:
        return service.revoke(token_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Token '{token_id}' was not found.") from exc
