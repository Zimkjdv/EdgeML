# API

## `GET /api/models`

Returns every valid model manifest discovered under the configured models root.

## `POST /api/predict`

Multipart form fields:

- `model_id`: model identifier from `GET /api/models`.
- `file`: a UTF-8 CSV file.

The request validates its size and CSV headers, runs a prediction, and returns a CSV attachment containing the original input columns and the manifest's `prediction_column`. The response is intentionally stateless: the browser uses the returned CSV for preview and download.

Errors use JSON with `detail` and appropriate HTTP status codes: 400 for invalid input, 404 for an unknown model, and 422 for schema/type validation failures.

