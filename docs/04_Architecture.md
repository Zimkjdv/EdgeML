# Architecture

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

The current frontend polls individual training jobs and displays their progress, but does not administer queue depth, worker capacity, retry attempts, or dead-letter jobs. A future Queue Operations UI will expose those read-oriented metrics and controlled retry/requeue/cancel actions.

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

The training module supports regression and classification. A user selects a target and explicitly checks feature columns. `TrainingService` fits imputers and categorical encoders inside a sklearn `Pipeline`, so each cross-validation fold fits preprocessing only from its training partition. The frontend exposes estimator-specific overrides incrementally: Gradient Boosting currently supports `n_estimators` and `learning_rate`, while XGBoost exposes its existing parameter set. Empty fields preserve estimator defaults. The pipeline is serialized as one artifact and published only after evaluation.

Training executes as a local background job. The job record persists queued/running/completed/failed status and stage progress so the UI can show real server-side progress rather than simulated client progress. This is intentionally a lightweight local implementation; a future multi-user deployment will replace it with a queue and worker service.

Regression evaluation uses R² as its primary model score. Detailed evaluation also records MAE, MAPE (%), RMSE, NRMSE, maximum error, target mean, and Pearson correlation (R). R² and R should be interpreted with the dataset context; EdgeML presents metrics rather than claiming a universal quality threshold.

Model manifests use the actual pandas dtype of each selected feature. Prediction validation therefore knows which uploaded CSV columns must be numeric, while categorical columns continue through the fitted encoder. Rows with missing required feature values are removed before inference; the history row count records only rows actually predicted.

Prediction accepts an optional Ground Truth column. The service prefers the manifest target when it is present, or accepts an explicitly selected column (commonly the last CSV column). Ground Truth is never included in the feature frame. When selected, the service calculates regression or classification metrics and adds row-level error/correctness columns to the returned CSV; regression prediction and error values are rounded to four decimal places for readability while aggregate metrics use full precision. Headers carry the aggregate metrics so the API remains a direct CSV response.

XGBoost is used through `XGBRegressor` inside this trusted sklearn pipeline. The Prediction Server therefore uses the existing sklearn artifact adapter while retaining an XGBoost dependency in its runtime image.
