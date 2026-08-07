# API

## `GET /api/models`

Returns every valid model manifest discovered under the configured models root.

## `POST /api/predict`

Multipart form fields:

- `model_id`: model identifier from `GET /api/models`.
- `file`: a UTF-8 CSV file.

The request validates its size and CSV headers, runs a prediction, and returns a CSV attachment containing the original input columns and the manifest's `prediction_column`. The response is intentionally stateless: the browser uses the returned CSV for preview and download.

Errors use JSON with `detail` and appropriate HTTP status codes: 400 for invalid input, 404 for an unknown model, and 422 for schema/type validation failures.

## Dataset and training APIs

- `GET /api/datasets`: list uploaded datasets.
- `POST /api/datasets`: upload a CSV and produce a column profile. UTF-8, UTF-8 BOM, CP950, and Big5 are accepted.
- `GET /api/datasets/{dataset_id}`: retrieve columns, inferred ML types, missing values, IQR outliers, and numeric statistics.
- `POST /api/training`: train a regression pipeline from a selected target and checked feature columns.
- `GET /api/trained-models`: list draft and published training artifacts.
- `POST /api/trained-models/{model_id}/publish`: validate and publish a draft model package to the prediction catalog.

The initial training algorithms are Random Forest, Gradient Boosting, XGBoost, and AdaBoost regressors. Training persists the full preprocessing and model pipeline as one trusted `model.pkl` artifact.
