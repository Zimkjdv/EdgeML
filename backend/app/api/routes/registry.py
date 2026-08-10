from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.dependencies import get_model_registry_service
from app.domain.errors import ModelNotFoundError
from app.domain.schemas import ModelRegistrySummary
from app.services.model_registry_service import ModelRegistryService

router = APIRouter()


class ModelRegistryStatusRequest(BaseModel):
    status: Literal["active", "disabled"]


@router.get("/model-registry", response_model=list[ModelRegistrySummary])
def list_registry(service: ModelRegistryService = Depends(get_model_registry_service)) -> list[ModelRegistrySummary]:
    return service.list()


@router.patch("/model-registry/{model_id}/status", response_model=ModelRegistrySummary)
def update_registry_status(
    model_id: str,
    request: ModelRegistryStatusRequest,
    service: ModelRegistryService = Depends(get_model_registry_service),
) -> ModelRegistrySummary:
    try:
        return service.set_status(model_id, request.status)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/model-registry/{model_id}", status_code=204)
def unregister_model(model_id: str, service: ModelRegistryService = Depends(get_model_registry_service)) -> None:
    try:
        service.unregister(model_id)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
