from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Query

from app.api.dependencies import get_dataset_service, get_dataset_ingestion
from app.core.config import get_settings
from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.domain.training_schemas import DatasetDetail, DatasetRenameRequest, DatasetSummary, DatasetPreview
from app.services.dataset_service import DatasetService
from app.services.dataset_ingestion import DatasetIngestion

router = APIRouter(prefix="/datasets")


@router.get("", response_model=list[DatasetSummary])
def list_datasets(service: DatasetService = Depends(get_dataset_service)) -> list[DatasetSummary]:
    return service.list()


@router.post("", response_model=DatasetDetail, status_code=201)
async def upload_dataset(
    file: UploadFile = File(...), service: DatasetService = Depends(get_dataset_service),
    ingestion: DatasetIngestion = Depends(get_dataset_ingestion),
) -> DatasetDetail:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="只接受 CSV 檔案。")
    content = await file.read(get_settings().max_upload_bytes + 1)
    if len(content) > get_settings().max_upload_bytes:
        raise HTTPException(status_code=400, detail="CSV 超過系統設定的大小限制。")
    try:
        return await ingestion.upload(service, file.filename, content)
    except PredictionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{dataset_id}", response_model=DatasetDetail)
def get_dataset(dataset_id: str, service: DatasetService = Depends(get_dataset_service)) -> DatasetDetail:
    try:
        return service.get(dataset_id)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PredictionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{dataset_id}/preview", response_model=DatasetPreview)
def preview_dataset(dataset_id: str, offset: int = Query(0, ge=0, le=10_000_000),
                    limit: int = Query(50, ge=1, le=100),
                    service: DatasetService = Depends(get_dataset_service)) -> DatasetPreview:
    try:
        return service.preview(dataset_id, offset, limit)
    except ModelNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PredictionValidationError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.patch("/{dataset_id}", response_model=DatasetDetail)
def rename_dataset(dataset_id: str, request: DatasetRenameRequest, service: DatasetService = Depends(get_dataset_service)) -> DatasetDetail:
    try:
        return service.rename(dataset_id, request.name)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PredictionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: str, service: DatasetService = Depends(get_dataset_service)) -> None:
    try: service.delete(dataset_id)
    except ModelNotFoundError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PredictionValidationError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
