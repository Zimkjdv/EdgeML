# API

## Post-training test evaluation

- `POST /api/trained-models/{model_id}/evaluate-csv`: multipart form with `file` (UTF-8 CSV, optional BOM). Uses the configured CSV file limit; unsupported extension/oversize returns 400, missing model 404, invalid CSV/columns/values or no usable rows 422. Parsing/inference runs in the bounded thread pool. The raw upload is not persisted or registered as a dataset.
- `POST /api/trained-models/{model_id}/evaluate`: existing JSON request `{ "dataset_id": "..." }` uses a stored dataset.

Both require normal API/browser authentication, work for Draft/Published models and return `{ "metrics": { ... }, "context": { "source": "csv|dataset", "source_name": "...", "dataset_id": null, "input_rows": 100, "evaluated_rows": 98, "dropped_rows": 2, "evaluated_at": "..." } }`. The same context is saved under model detail `test_evaluation`. All training feature columns and the model target are required. Success atomically replaces test scores only; a failed test preserves previous scores, validation metrics and artifacts.

Prediction CSV uses UTF-8 (optional BOM), comma delimiters, double-quoted multiline fields and doubled quote escaping. Headers must be nonempty/unique and every data record must match the header width. Header names are preserved exactly. Blank physical lines are skipped; records such as `,,` and quoted empty fields count as rows. Required-feature and selected Ground Truth NA values remove rows; unused columns do not. The explicit, case-sensitive NA tokens are empty string, `#N/A`, `#N/A N/A`, `#NA`, `-1.#IND`, `-1.#QNAN`, `-NaN`, `-nan`, `1.#IND`, `1.#QNAN`, `<NA>`, `N/A`, `NA`, `NULL`, `NaN`, `None`, `n/a`, `nan`, `null`. Spaces are not automatically NA (invalid numeric spaces still fail numeric validation). The same parser is used for frontend preview/counting; shared fixture tests verify both implementations. Successful responses retain `X-Prediction-Dropped-Rows` as the authoritative result.

Training requests accept `validation_strategy` (`random`, `time`, `group`, default `random`), `validation_column` (required for time/group), and `time_gap` (default 0, measured in distinct timestamps). `GET /api/trained-models/{model_id}` includes `validation_context` with strategy and total/evaluated/excluded row counts. Time validation excludes the initial warm-up rows from scores. See [Regression evaluation](12_Regression_Metrics.md).

Feature importance: `GET /api/trained-models/{model_id}/feature-importance?format=json` (or `csv`) returns the saved ranking. `POST` to the same endpoint computes or refreshes it using the original source dataset. See [Feature importance API](11_Feature_Importance.md#api) for response metadata and examples.

## Parameter optimization

`GET /api/optimization/models` and `POST /api/optimization/simulate` support target-directed regression simulation, fixed/adjustable features, and 1–5 recommendations. Use the `source=trained` (default) or `source=registry` query parameter. These endpoints use existing API authentication. See [Parameter optimization](07_Parameter_Optimization.md) for request/response details and search limits.

## Observability endpoints

- `GET /health` and `GET /health/live`: process liveness checks. Both return `{"status":"ok"}` while the API process is running.
- `GET /health/ready`: validates the model, dataset, trained-model, registry storage paths, and Redis queue connectivity. Returns `503` when a required check fails.
- `GET /metrics`: Prometheus text exposition containing HTTP request, prediction, training-job, and active-registry-model metrics.

Every HTTP response includes an `X-Request-ID` header. Clients may provide a bounded `X-Request-ID` value to correlate logs; otherwise EdgeML generates one. Structured access logs include the request ID, route, status code, and duration without logging uploaded CSV contents.

## Optional API authentication

Integration clients send `Authorization: Bearer <token>` or `X-API-Key: <token>` using `EDGEML_API_TOKEN` or a managed token. Browser users sign in with separate web credentials and use an HttpOnly session cookie; writes additionally require `X-CSRF-Token`. Business APIs require authentication by default, including after all tokens expire or are revoked. Health probes remain public. Anonymous development requires explicit `EDGEML_ANONYMOUS_API=true` with no web password or bootstrap token; managed-token counts never toggle this policy. Frontend bundles no longer contain API tokens. The public `/api/auth/session` status/login/logout endpoints implement the browser session lifecycle; see [Web authentication](10_Web_Authentication.md).

### Token management APIs

The frontend **API Token Management** page uses the following endpoints. The bootstrap token or an existing token with the `tokens:manage` scope is required:

- `POST /api/auth/tokens`: create a token with a name, optional expiry, and `api`／`tokens:manage` scopes. The `api` scope is required for regular `/api/*` routes; `tokens:manage` is sufficient only for token administration. The raw token is returned only in this response.
- `GET /api/auth/tokens`: list token metadata without raw values or hashes.
- `DELETE /api/auth/tokens/{token_id}`: revoke a token. Revoked tokens cannot authenticate future requests.

Example creation request:

```json
{
  "name": "CI integration",
  "scopes": ["api"],
  "expires_at": "2027-01-01T00:00:00Z"
}
```

Token metadata is stored in the configured SQLite file (`backend/data/api_tokens.sqlite3` by default). The raw token is never persisted. On a fresh deployment, set `EDGEML_API_TOKEN` before opening the management page so the first managed token can be created.

### Windows CMD smoke test

After restarting the local launcher with the `.env` token, use these commands. For the full Docker runtime, replace port `8000` with `8010`.

Health probes are anonymous:

```cmd
curl.exe -i http://localhost:8000/health
```

An API request without a token should return `401`:

```cmd
curl.exe -i http://localhost:8000/api/models
```

Call the API with either supported authentication header:

```cmd
curl.exe -i http://localhost:8000/api/models ^
  -H "Authorization: Bearer your-env-token"

curl.exe -i http://localhost:8000/api/models ^
  -H "X-API-Key: your-env-token"
```

Create a managed token with the bootstrap token. The returned `token` value is shown only once:

```cmd
curl.exe -X POST "http://localhost:8000/api/auth/tokens" ^
  -H "Authorization: Bearer your-env-token" ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"CLI Test Token\",\"scopes\":[\"api\",\"tokens:manage\"]}"
```

Use that returned value in place of `your-managed-token` for subsequent `/api/*` requests. If `.env` changes, restart local services or recreate Docker Backend with the new environment. The frontend does not embed tokens.

## `GET /api/models`

Returns every active model registered in the configured model registry.

## Model ID lookup APIs

- `GET /api/models/ids`: returns a JSON array containing the IDs of all active models. Use this endpoint when a client needs to populate a model-ID selector or cache the available IDs.
- `GET /api/models/by-name/{model_name}`: resolves a model display name to its ID. The `by-name` segment intentionally uses kebab-case for URL readability and should remain unchanged for API clients. Matching ignores leading/trailing whitespace and letter case. The response is `{ "name": "HousePrice", "id": "house-price-v1" }`; an unknown name returns `404`.

Examples:

```text
GET /api/models/ids
GET /api/models/by-name/HousePrice
```

`GET /api/models/ids` response example:

```json
["house-price-v1", "credit-risk-v1", "customer-churn-v1"]
```

## `POST /api/predict`

Multipart form fields:

- `model_id`: model identifier from `GET /api/models`.
- `file`: a UTF-8 CSV file.
- `ground_truth_column` (optional): the answer/target column to score. If omitted, EdgeML automatically uses the manifest target when that column exists in the uploaded CSV. Send an empty value to force prediction-only mode.
- `training_range_policy` (optional): `none` (default, allow extrapolation) or `drop` (exclude rows with any numeric input outside the saved training min/max; inclusive boundaries).

The request validates its size and CSV headers, drops rows with missing required feature values (and missing Ground Truth values when evaluation is enabled), runs a prediction on the remaining rows, and returns a CSV attachment containing the original input columns and the manifest's `prediction_column`. Regression prediction and `prediction_error` values in the returned CSV are rounded to four decimal places; evaluation metrics still use the full-precision predictions. Regression files with Ground Truth also receive `prediction_error`; classification files receive `prediction_correct`. If every row is removed, the request returns a validation error. The response is intentionally stateless: the browser uses the returned CSV for preview and download.

Response headers include `X-Prediction-Metrics` (JSON), `X-Prediction-Ground-Truth` (URL-encoded column name), `X-Prediction-Dropped-Rows` (total excluded rows), and `X-Prediction-Out-Of-Range-Rows` (the training-range subset of that total). Metrics are populated when Ground Truth is available. Regression metrics include MAE, MAPE (%), RMSE, maximum error, R², and Pearson R. Classification metrics include accuracy, weighted precision, weighted recall, and weighted F1.

Every successful request also writes prediction metadata to the configured history repository. Uploaded CSV contents and prediction outputs are not retained.

Errors use JSON with `detail` and appropriate HTTP status codes: 400 for invalid input, 404 for an unknown model, and 422 for schema/type validation failures.

CSV and JSON share numeric validation: integer dtypes require finite, mathematically integral values within their signed/unsigned bit range. `2.0` and `2e1` are accepted; `1.9`, infinity, invalid numeric text and overflow return `422` naming the column. Floating dtypes also reject infinity and conversion overflow. Actual missing values still follow the existing row-drop policy; invalid nonmissing values are not silently dropped even if another column in the same row is missing. Integer parsing preserves exact int64/uint64 values when mixed with missing rows; callers must also preserve precision before submitting JSON (for example, send large integers as decimal strings from JavaScript).

## `POST /api/predict/json`

For the standalone MySQL source/output examples (whole table or required time range), see [DB Prediction client](14_DB_Prediction_Client.md). Both entrypoints process all matching source rows in batches by default; `--limit` is optional. These clients preview-filter locally and opt into the same training-range policy on Prediction; no separate filtering endpoint is needed.

Use this endpoint when the caller already has data from a database, service, or in-memory application. It accepts JSON instead of a CSV upload:

```json
{
  "model_id": "house-price-v1",
  "source_name": "sales-service",
  "data": [
    {"Area": 80, "Room": 2, "Age": 15},
    {"Area": 120, "Room": 3, "Age": 8}
  ]
}
```

`ground_truth_column` is optional and enables evaluation when each data item includes that field. The response contains `model_id`, `model_name`, `prediction_column`, a `records` array with the original fields plus predictions, `metrics`, `ground_truth_column`, `dropped_rows`, and `out_of_range_rows`. Rows missing required feature values (or the selected Ground Truth value) are excluded and counted in `dropped_rows`. The endpoint writes metadata-only prediction history with `source_name` (or `json-api` when omitted). For backward compatibility, the initial `records` request field is still accepted; new clients should use `data`.

### Optional training-range filtering (CSV and JSON)

Supply `"training_range_policy": "drop"` in the JSON body, or `training_range_policy=drop` in the CSV multipart form. The server filters numeric features against `minimum`/`maximum` stored in the trusted model manifest's `feature_defaults`; callers do **not** need to fetch metadata first. Bounds are inclusive. Any out-of-range numeric feature excludes the whole row; a row with multiple out-of-range features is counted once. Required/Ground Truth missing rows are removed first. `out_of_range_rows` is included in `dropped_rows`, not additional to it. Remaining rows keep their original order and extra identifiers; integrations must match retained row identifiers, not zip results against unfiltered source rows.

With `drop`, absent/invalid numeric training snapshots or an empty surviving batch return `422` before inference/history. The server does not read a database or recompute bounds from a mutable dataset. Type errors and nonfinite nonmissing values still return `422`; this policy is not a general invalid-value sanitizer. Optional missing inputs stay available for preprocessing, and categorical features do not get a min/max or membership filter. Evaluation only uses retained rows. Models without saved bounds continue to work with the default `none`.

Training min/max are observed data ranges, **not** process safety limits or proof that an outside value is erroneous. Therefore filtering is opt-in and existing CSV/JSON callers and the Prediction UI keep their previous behavior unless they send `drop`.

JSON requests are limited by `EDGEML_MAX_JSON_BODY_BYTES` (default 10 MiB), `EDGEML_MAX_JSON_RECORDS` (default 10,000), `EDGEML_MAX_JSON_COLUMNS` (default 256), and `EDGEML_MAX_JSON_VALUE_CHARS` (default 10,000). Requests over a configured limit return `413`.

## Model registry APIs

- `GET /api/model-registry`: list all registered model packages and lifecycle status.
- `PATCH /api/model-registry/{model_id}/status`: enable or disable a registered model in the Prediction selector.
- `DELETE /api/model-registry/{model_id}`: remove a registry entry without deleting the trusted package files.

The **Model Registry → Model ID** column displays each registry response's `id`. Its icon-only copy button (tooltip and accessible label: **Copy model ID**) copies the full value, including IDs visually shortened by the table. Supply that value as `model_id` in `POST /api/predict` or `POST /api/predict/json`. The registry response's `package_name` is an internal artifact directory, not the API identifier: for example, `HousePrice` is the directory and `house-price-v1` is the ID. No API fields or existing model IDs have changed. Registry rows include disabled models, but only active IDs are accepted for prediction.

Automatic copying uses the browser Clipboard API where allowed, with a legacy copy fallback for HTTP intranet pages. If browser policy blocks both methods, the UI reports failure and the ID text can be selected/copied manually. The action copies the ID only, without JSON formatting, labels or surrounding quotes.

The UI keeps the ID column at a compact fixed width and visually truncates long IDs with an ellipsis; this is a CSS-only display change. The tooltip, selectable text and clipboard value still contain the original full ID. Model identifiers and API request/response fields are unchanged.

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

Training, training-time external tests, later model evaluation and feature-importance recomputation share a row policy: always drop missing targets; when saved `numeric_imputer` is `drop`, also drop missing values in any selected feature (numeric or categorical). Otherwise the fitted pipeline handles feature gaps. Unused columns do not affect eligibility. Training validates fold sizes and classification class counts after cleaning. No usable rows produces `422`; background jobs persist a validation failure. A failed evaluation does not replace previously saved scores. Automatic feature importance additionally needs at least two usable rows.

Manual dead-letter replay persists a queued job (including `replay_pending=true`) under the shared dispatch/ownership locks before atomically moving its ID in Redis. The flag clears when a Worker starts the attempt. If file persistence fails, the original job and dead-letter entry remain intact. If Redis fails or the API process exits after preparation, the job may remain queued in its JSON file but listed in dead-letter; retry the same replay endpoint after recovery. If dispatch already committed, inspect the job/queue instead: replay returns `404` once the ID is no longer dead-lettered, and does not enqueue a duplicate. Still-processing jobs return `409`; infrastructure failures return `503`. Attempt history is retained. This is recoverable at-least-once dispatch, not a transaction spanning Redis and the filesystem.

Random Forest, Gradient Boosting, XGBoost, and Logistic Regression hyperparameters are optional. Random Forest accepts `n_estimators`, `min_samples_leaf`, `max_depth`, `min_samples_split`, and `max_leaf_nodes`; omitted parameters use estimator defaults. EdgeML only fixes random seeds and CPU worker counts where applicable for reproducibility during local development.
