# API

## Observability endpoints

- `GET /health` and `GET /health/live`: process liveness checks. Both return `{"status":"ok"}` while the API process is running.
- `GET /health/ready`: validates the model, dataset, trained-model, registry storage paths, and Redis queue connectivity. Returns `503` when a required check fails.
- `GET /metrics`: Prometheus text exposition containing HTTP request, prediction, training-job, and active-registry-model metrics.

Every HTTP response includes an `X-Request-ID` header. Clients may provide a bounded `X-Request-ID` value to correlate logs; otherwise EdgeML generates one. Structured access logs include the request ID, route, status code, and duration without logging uploaded CSV contents.

## `GET /api/models`

Returns every active model registered in the configured model registry.

## `POST /api/predict`

Multipart form fields:

- `model_id`: model identifier from `GET /api/models`.
- `file`: a UTF-8 CSV file.
- `ground_truth_column` (optional): the answer/target column to score. If omitted, EdgeML automatically uses the manifest target when that column exists in the uploaded CSV. Send an empty value to force prediction-only mode.

The request validates its size and CSV headers, drops rows with missing required feature values (and missing Ground Truth values when evaluation is enabled), runs a prediction on the remaining rows, and returns a CSV attachment containing the original input columns and the manifest's `prediction_column`. Regression prediction and `prediction_error` values in the returned CSV are rounded to four decimal places; evaluation metrics still use the full-precision predictions. Regression files with Ground Truth also receive `prediction_error`; classification files receive `prediction_correct`. If every row is removed, the request returns a validation error. The response is intentionally stateless: the browser uses the returned CSV for preview and download.

When Ground Truth is available, evaluation metrics are returned in the response headers: `X-Prediction-Metrics` (JSON), `X-Prediction-Ground-Truth` (URL-encoded column name), and `X-Prediction-Dropped-Rows`. Regression metrics include MAE, MAPE (%), RMSE, maximum error, R², and Pearson R. Classification metrics include accuracy, weighted precision, weighted recall, and weighted F1.

Every successful request also writes prediction metadata to the configured history repository. Uploaded CSV contents and prediction outputs are not retained.

Errors use JSON with `detail` and appropriate HTTP status codes: 400 for invalid input, 404 for an unknown model, and 422 for schema/type validation failures.

## Model registry APIs

- `GET /api/model-registry`: list all registered model packages and lifecycle status.
- `PATCH /api/model-registry/{model_id}/status`: enable or disable a registered model in the Prediction selector.
- `DELETE /api/model-registry/{model_id}`: remove a registry entry without deleting the trusted package files.

## `GET /api/prediction-history`

Returns successful prediction records in reverse chronological order. Each record contains its identifier, model identifier and name, sanitized source filename, input row count, and UTC creation time. The history contains metadata only.

## Dataset and training APIs

- `GET /api/datasets`: list uploaded datasets.
- `POST /api/datasets`: upload a CSV and produce a column profile. UTF-8, UTF-8 BOM, CP950, and Big5 are accepted.
- `GET /api/datasets/{dataset_id}`: retrieve columns, inferred ML types, missing values, IQR outliers, and numeric statistics.
- `PATCH /api/datasets/{dataset_id}`: update a dataset display name without renaming its original CSV file.
- `DELETE /api/datasets/{dataset_id}`: remove a stored source CSV and its profile metadata.
- `POST /api/training`: train a regression or classification pipeline from a selected target and checked feature columns.
- `POST /api/training/jobs`: enqueue a training job; `GET /api/training/jobs/{job_id}` returns persisted progress, worker metadata, and status.
- `POST /api/training/jobs/{job_id}/cancel`: cancel a queued job before a worker claims it. Returns `409` when the job is already running or terminal.
- `GET /api/queue/status`: return queued, processing, and dead-letter counts plus queued/processing job IDs for the configured training queue.
- `GET /api/queue/dead-letter`: list failed jobs retained for operator inspection, including attempt count and failure metadata.
- `POST /api/queue/dead-letter/{job_id}/requeue`: move a dead-letter job back to the primary queue for manual replay while preserving its attempt history.
- `GET /api/trained-models`: list draft and published training artifacts.
- `PATCH /api/trained-models/{model_id}`: update a model display name and its published manifest when applicable.
- `DELETE /api/trained-models`: delete one or more Draft/Published model artifacts by id.
- `POST /api/trained-models/{model_id}/publish`: validate and publish a draft model package to the prediction catalog.
- `POST /api/trained-models/{model_id}/evaluate`: evaluate an existing trained model with a separately uploaded Dataset.

Training supports Random Forest, Gradient Boosting, XGBoost, and AdaBoost regression, plus classifier variants for those algorithms and Logistic Regression classification. Training persists the full preprocessing and model pipeline as one trusted `model.pkl` artifact.

Random Forest, Gradient Boosting, XGBoost, and Logistic Regression hyperparameters are optional. Random Forest accepts `n_estimators`, `min_samples_leaf`, `max_depth`, `min_samples_split`, and `max_leaf_nodes`; omitted parameters use estimator defaults. EdgeML only fixes random seeds and CPU worker counts where applicable for reproducibility during local development.
