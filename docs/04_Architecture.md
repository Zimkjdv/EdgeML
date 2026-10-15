# Architecture

UI text and user data are separate: explicit typed translation keys replace trained-page DOM rewriting, with one-pass parameter interpolation and raw data rendering. See [i18n data safety](17_I18n_Data_Safety.md).

Frontend composition and request ownership are documented in [Frontend lifecycle](16_Frontend_Lifecycle.md): lazy pages, typed JSON API client, shared workspace composables, last-request-wins detail loading and resumable, page-scoped training polling.

Inference depends on `PredictorProvider`; composition supplies a per-process bounded LRU of synchronized `BasePredictor` runtimes, not framework-specific adapters in services. Active Registry resolution remains per request. Admission, fingerprints, lifecycle invalidation, thread safety and measured limits are detailed in [Runtime performance](15_Runtime_Performance.md). Dataset profiling uses a separate bounded executor and preserves its slot through client cancellation until work actually ends; it does not block the ASGI event loop.

JSON Prediction has a pure ASGI body-limit middleware before routing/JSON decoding. It checks declared size early and accumulates actual bytes into a bounded buffer, then replays the accepted body to FastAPI. Missing/chunked/understated Content-Length therefore cannot bypass the Backend cap. CORS and request-context middleware wrap this layer, preserving headers and HTTP logging on `413`. The typed request accepts scalar finite values; a Prediction-specific validation handler returns JSON-safe errors without reflecting payloads. Routers retain HTTP limit responses and services retain feature/model/evaluation validation.

CSV prediction reads the upload asynchronously and dispatches synchronous Pandas/model work to Starlette's bounded thread pool (`run_in_threadpool`). Routers still only translate HTTP; prediction validation and inference remain in `PredictionService`. Health and other API requests can respond while a CSV prediction is running. The existing shared thread-pool capacity bounds concurrency; CPU throughput still depends on model/native-library threads and available resources.

## Reliability boundaries (2026-09-21)

- Publication uses a validated ID path, staged copy and atomic directory rename; display names are metadata only. Existing published artifacts are not recursively deleted before republishing.
- Docker uses the shared `/app/data/published_models` store. Image seeds are copied only when absent; legacy migration runs before container recreation. See [Deployment](05_Deployment.md#model-storage-and-reliability-upgrade).
- `FileModelRegistry` retains its JSON format, with a reentrant cross-process OS lock around each complete mutation transaction, unique temporary files, fsync and atomic replacement. Invalid indexes are preserved and reported, not silently reset.
- Redis job ownership is protected by OS locks on the common jobs Volume. Dispatch and recovery share a lock; recovery probes per-job locks and only requeues abandoned entries. OS termination releases ownership without a wall-clock heartbeat timeout. Single-host/shared-local-volume is required; this is not a distributed multi-host lease protocol.
- Dead-letter replay serializes preparation and dispatch under shared ownership locks, writes complete job JSON atomically, then performs the Redis list move in Lua. A persisted replay marker makes an interrupted preparation retryable. Remaining transaction work for other JSON stores is tracked in [ROADMAP](../ROADMAP.md).

```text
Vue UI -> FastAPI router -> PredictionService -> ModelCatalog -> BasePredictor plugin
                                            -> CSV validation
                                            -> optional Ground Truth evaluation
                                            -> PredictionHistoryRepository

Vue UI -> FastAPI router -> DatasetService -> trusted CSV + profile metadata
                       -> TrainingService -> sklearn Pipeline artifact -> ModelCatalog publication
```

Routers only handle HTTP. `PredictionService` coordinates validation and prediction. `ModelCatalog` is the application boundary for model discovery and lookup; v0.5 uses `FileModelRegistry` to persist registry metadata while model packages remain trusted files under `ml_models/`. `PredictorFactory` chooses a `BasePredictor` implementation from the manifest's `framework` field.

The v0.7.1 observability layer is cross-cutting: `RequestContextMiddleware` adds bounded request IDs, structured JSON access logs, and HTTP metrics without exposing CSV contents. Health routes expose liveness, storage-backed readiness, and Prometheus metrics. Training and prediction services record outcome counters and duration metrics.

In v0.7.2, `TrainingJobQueue` is the application boundary for asynchronous training dispatch. The API persists the request and initial job state under `training_jobs/`, then enqueues only the job ID. A separate Redis-backed worker consumes, executes, and acknowledges jobs through `TrainingService`; the API and worker share the job and trained-model storage volume. The queue uses an at-least-once delivery model and requeues jobs left in the processing list after worker restart. The v0.7.3 queue-operations step adds bounded exponential backoff for transient infrastructure failures while deterministic validation and model errors remain terminal; terminal failures are routed to a dedicated Redis dead-letter list for later inspection or replay. Worker SIGTERM/SIGINT handlers stop new consumption, allow the current job lifecycle to finish, and leave an in-flight retry recoverable on the next worker start.

The frontend polls individual training jobs and now includes a Queue Operations page for queue depth, queued/processing IDs, retry attempts, dead-letter inspection, manual requeue, and queued-job cancellation. Worker-capacity controls remain a future operational enhancement.

Manual replay never writes job state after dispatch. A worker can immediately consume a prepared `queued` job. The dispatch lock and per-job ownership lock also exclude concurrent replay and a still-active worker; all participants must share the local jobs volume. A failed atomic file write preserves the previous record. If Redis dispatch has an ambiguous outcome, the prepared state is retained: either the ID is already queued, or it remains in dead-letter for an explicit retry. This does not provide exactly-once execution or a distributed transaction. See the API document for retry/status behavior.

## Runtime modes

Docker Compose is the recommended runtime and starts the frontend, FastAPI backend, Redis queue, and training worker together. Local development may run the FastAPI server and Vue dev server directly while Redis and the training worker run through Docker. Prediction can run with only the API process, but asynchronous training requires both Redis and a worker.

The registry stores package metadata and an active/disabled status in `backend/data/model_registry.json`. Existing model packages are bootstrapped into the registry on first startup. Disabling a model removes it from the Prediction selector without deleting its artifact package; unregistering only removes the registry entry.

`PredictionService` depends on the `PredictionHistoryRepository` abstraction and records metadata only after a prediction succeeds. The initial `FilePredictionHistoryRepository` adapter uses JSON Lines local persistence. It can be replaced by a database-backed adapter without changing the service or HTTP route.

Each runtime adapter implements `load`, `predict`, `predict_proba`, `explain`, and `metadata`. v0.1 includes `SklearnPredictor`; XGBoost, LightGBM, CatBoost, ONNX, TensorFlow, and Torch are future plugins.

## Model package

```text
ml_models/HousePrice/
├─ model.pkl
├─ preprocess.pkl       # optional; prefer a single serialized sklearn Pipeline
├─ metadata.json
├─ requirements.txt     # documentation and build-time dependency declaration only
└─ README.md
```

Artifacts are trusted deployment inputs. Model packages are mounted or baked into an image by an operator; the API never accepts serialized models.

The executable development examples are built together with `python scripts/build_example_models.py`.

## Training module

### Training audit and classification contract

Training captures training/external dataset bytes under the dataset lock before fitting. Those immutable in-memory frames feed validation, final fit, external evaluation and importance; a later file change cannot silently change an external test within that run. `TrainingProvenance` version `training-v1` persists in record.json and the published manifest. It records source SHA256 (raw bytes, including encoding/newlines), dataset IDs/names, original row/column counts, selected target/features, runtime package versions and `get_params(deep=True)` values from the fitted pipeline. Parameter objects are class descriptions, not executable code or repr strings with machine addresses. XGBoost additionally stores its fitted booster configuration to resolve Python `None` defaults. This is an audit snapshot, not automatic environment reconstruction or a guarantee of cross-hardware determinism.

Validation audit saves strategy/column/gap/seed, usable/evaluated/excluded rows, row-order SHA256 and each fold's train/validation counts and index hashes. Indices refer to zero-based original CSV data-row positions (excluding the header) after cleaning/reordering; no row values or full index lists are duplicated. Random folds use seed 42; nonrandom seed is null. Splits are materialized once and shared by evaluation/audit, preserving the existing fold-local preprocessing rule.

New classification records use `evaluation_version=classification-oof-v1`. Primary accuracy, precision, recall and F1 use the pooled OOF predictions, not an unweighted mean of fold metrics. Precision/recall/F1 are weighted by actual-class support, `zero_division=0`; `cv_*_mean` remains separate. Binary OOF ROC AUC uses probabilities for the second sorted training class; it is absent for multiclass. External test ROC AUC is currently not computed. Regression stays `oof-v2` and its detailed formulas are unchanged.

`validation_confusion` and `test_confusion` are separate from numeric metric dictionaries. Their contract is `{labels, matrix, sample_count, binary}`: rows=actual, columns=predicted, both in identical explicit label order, with integer nonnegative counts summing to sample_count. Labels retain JSON scalar types. Training class order comes from the classifier/sorted training labels; unseen external labels are appended deterministically and count as errors. If the resulting matrix has exactly two classes, `binary` names negative=labels[0], positive=labels[1], and TN/FP/FN/TP. For multiclass it is null. No label is implicitly treated as approved/defective/positive based on its text. `EDGEML_CLASSIFICATION_MAX_CLASSES` bounds total labels, default 100 (2–200); overflow returns a validation error before allocating the matrix. Export this variable for local processes; Compose forwards root .env to backend/worker.

Later external evaluation saves test checksum/context/matrix only, preserving validation audit and artifact. Legacy records lacking provenance or matrices remain unavailable; retraining produces new validation audit/matrix, and supplemental evaluation can produce a new test matrix. Lists derive legacy accuracy/F1 from already saved metrics without recalculation. Native i18n audit/list/matrix components are excluded from legacy DOM text replacement; the wider i18n refactor remains on ROADMAP.

Dataset preview is server-paginated with 50 rows by default, maximum 100. It preserves raw cell text (leading zeroes, decimal notation, large nullable integers and Chinese multiline cells), mapping the shared CSV NA tokens to null. Vue escapes text, never renders cell HTML. Responses do not contain the entire CSV; the present file adapter still parses the size-limited source per request, not a streaming database or columnar query engine. Raw-content previews and profiling remain distinct.

The training module supports regression and classification. A user selects a target and explicitly checks feature columns. `TrainingService` fits imputers and categorical encoders inside a sklearn `Pipeline`, so each cross-validation fold fits preprocessing only from its training partition. The frontend exposes estimator-specific overrides incrementally: Gradient Boosting currently supports `n_estimators` and `learning_rate`, while XGBoost exposes its existing parameter set. Empty fields preserve estimator defaults. The pipeline is serialized as one artifact and published only after evaluation.

`clean_supervised_frame` owns eligibility for training, external tests, later evaluation and importance recomputation: remove missing targets, and in `drop` mode remove missing selected features, including categorical ones. Cross-validation size/class checks operate on the cleaned data. Empty inputs fail clearly before prediction; imputation stays inside the fitted Pipeline in other modes. Existing artifact scores are not automatically recalculated.

Training executes through the Redis-backed `TrainingJobQueue` and an independent worker. The API persists queued/running/completed/failed status and stage progress under `training_jobs/`, then enqueues only the job ID so the UI can show real server-side progress rather than simulated client progress. Docker Compose runs the Backend, Redis, and Worker as separate services; the hybrid launcher keeps Redis isolated while running the application processes locally. Runtime integration coverage and stronger multi-process persistence remain follow-up work.

Regression evaluation uses R² as its primary model score. Detailed evaluation also records MAE, MAPE (%), RMSE, NRMSE, maximum error, target mean, and Pearson correlation (R). R² and R should be interpreted with the dataset context; EdgeML presents metrics rather than claiming a universal quality threshold.

Model manifests use the actual pandas dtype of each selected feature. Prediction validation therefore knows which uploaded CSV columns must be numeric, while categorical columns continue through the fitted encoder. Rows with missing required feature values are removed before inference; the history row count records only rows actually predicted.

Numeric validation checks finite values, integer integrality and dtype bounds before conversion. Decimal parsing and nullable integer columns avoid float64 rounding for large integers with missing values. Invalid nonmissing values return `422` rather than truncating/wrapping. The authentication boundary similarly uses explicit configuration (`anonymous_api=false` by default), never active-token counts, for anonymous access; the browser session-status API uses the same policy.

Prediction accepts an optional Ground Truth column. The service prefers the manifest target when it is present, or accepts an explicitly selected column (commonly the last CSV column). Ground Truth is never included in the feature frame. When selected, the service calculates regression or classification metrics and adds row-level error/correctness columns to the returned CSV; regression prediction and error values are rounded to four decimal places for readability while aggregate metrics use full precision. Headers carry the aggregate metrics so the API remains a direct CSV response.

XGBoost is used through `XGBRegressor` inside this trusted sklearn pipeline. The Prediction Server therefore uses the existing sklearn artifact adapter while retaining an XGBoost dependency in its runtime image.
