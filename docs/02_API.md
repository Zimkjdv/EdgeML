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
- `PATCH /api/datasets/{dataset_id}`: update a dataset display name without renaming its original CSV file.
- `POST /api/training`: train a regression pipeline from a selected target and checked feature columns.
- `POST /api/training/jobs`: create a background training job; `GET /api/training/jobs/{job_id}` returns persisted progress and status.
- `GET /api/trained-models`: list draft and published training artifacts.
- `PATCH /api/trained-models/{model_id}`: update a model display name and its published manifest when applicable.
- `DELETE /api/trained-models`: delete one or more Draft/Published model artifacts by id.
- `POST /api/trained-models/{model_id}/publish`: validate and publish a draft model package to the prediction catalog.
- `POST /api/trained-models/{model_id}/evaluate`: evaluate an existing trained model with a separately uploaded Dataset.

The initial training algorithms are Random Forest, Gradient Boosting, XGBoost, and AdaBoost regressors. Training persists the full preprocessing and model pipeline as one trusted `model.pkl` artifact.

XGBoost hyperparameters are optional. Omitted parameters use XGBoost's native defaults; EdgeML only fixes a random seed and CPU worker count for reproducibility during local development.
