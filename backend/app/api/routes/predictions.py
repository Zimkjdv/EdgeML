from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.api.dependencies import get_prediction_service
from app.core.config import get_settings
from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.services.prediction_service import PredictionService

router = APIRouter()


@router.post("/predict", response_class=Response)
async def predict(
    model_id: str = Form(...),
    file: UploadFile = File(...),
    service: PredictionService = Depends(get_prediction_service),
) -> Response:
    settings = get_settings()
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail="CSV exceeds the configured upload size limit.")

    try:
        result = service.predict_csv(model_id=model_id, content=content)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PredictionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    headers = {"Content-Disposition": f'attachment; filename="{result.filename}"'}
    return Response(content=result.csv_content, media_type="text/csv; charset=utf-8", headers=headers)

