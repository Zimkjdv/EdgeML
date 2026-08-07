from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.dependencies import get_dataset_service
from app.core.config import get_settings
from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.domain.training_schemas import DatasetDetail, DatasetRenameRequest, DatasetSummary
from app.services.dataset_service import DatasetService

router = APIRouter(prefix="/datasets")


@router.get("", response_model=list[DatasetSummary])
def list_datasets(service: DatasetService = Depends(get_dataset_service)) -> list[DatasetSummary]:
    return service.list()


@router.post("", response_model=DatasetDetail, status_code=201)
async def upload_dataset(
    file: UploadFile = File(...), service: DatasetService = Depends(get_dataset_service)
) -> DatasetDetail:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="只接受 CSV 檔案。")
    content = await file.read(get_settings().max_upload_bytes + 1)
    if len(content) > get_settings().max_upload_bytes:
        raise HTTPException(status_code=400, detail="CSV 超過系統設定的大小限制。")
    try:
        return service.upload(file.filename, content)
    except PredictionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{dataset_id}", response_model=DatasetDetail)
def get_dataset(dataset_id: str, service: DatasetService = Depends(get_dataset_service)) -> DatasetDetail:
    try:
        return service.get(dataset_id)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{dataset_id}", response_model=DatasetDetail)
def rename_dataset(dataset_id: str, request: DatasetRenameRequest, service: DatasetService = Depends(get_dataset_service)) -> DatasetDetail:
    try:
        return service.rename(dataset_id, request.name)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: str, service: DatasetService = Depends(get_dataset_service)) -> None:
    try: service.delete(dataset_id)
    except ModelNotFoundError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc
