import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.api.dependencies import get_prediction_service
from app.core.observability import record_prediction
from app.core.config import get_settings
from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.domain.schemas import JsonPredictionOutput, JsonPredictionRequest, PredictionHistoryRecord
from app.services.prediction_service import PredictionService

router = APIRouter()


@router.get("/prediction-history", response_model=list[PredictionHistoryRecord])
def prediction_history(
    service: PredictionService = Depends(get_prediction_service),
) -> list[PredictionHistoryRecord]:
    return service.list_history()


@router.post("/predict/json", response_model=JsonPredictionOutput)
def predict_json(
    request: JsonPredictionRequest,
    service: PredictionService = Depends(get_prediction_service),
) -> JsonPredictionOutput:
    try:
        return service.predict_json(
            model_id=request.model_id,
            records=request.input_data,
            source_name=request.source_name,
            ground_truth_column=request.ground_truth_column,
        )
    except ModelNotFoundError as exc:
        record_prediction("not_found")
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PredictionValidationError as exc:
        record_prediction("validation_error")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        record_prediction("error")
        raise


@router.post("/predict", response_class=Response)
async def predict(
    model_id: str = Form(...),
    file: UploadFile = File(...),
    ground_truth_column: str | None = Form(None),
    service: PredictionService = Depends(get_prediction_service),
) -> Response:
    settings = get_settings()
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail="CSV exceeds the configured upload size limit.")

    try:
        result = service.predict_csv(
            model_id=model_id,
            content=content,
            source_filename=file.filename,
            ground_truth_column=ground_truth_column,
        )
    except ModelNotFoundError as exc:
        record_prediction("not_found")
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PredictionValidationError as exc:
        record_prediction("validation_error")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        record_prediction("error")
        raise

    record_prediction("success")

    encoded_filename = quote(result.filename, safe="")
    headers = {
        "Content-Disposition": f'attachment; filename="predictions.csv"; filename*=UTF-8\'\'{encoded_filename}',
        "X-Prediction-Metrics": json.dumps(result.metrics, separators=(",", ":")),
        # HTTP headers are Latin-1 in Starlette; percent-encode Chinese column names.
        "X-Prediction-Ground-Truth": quote(result.ground_truth_column or "", safe=""),
        "X-Prediction-Dropped-Rows": str(result.dropped_rows),
    }
    return Response(content=result.csv_content, media_type="text/csv; charset=utf-8", headers=headers)
