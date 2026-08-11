# EdgeML

Enterprise Edge Machine Learning Prediction Platform.

EdgeML is a self-hosted, plugin-oriented platform for batch predictions from CSV files. Its first milestone supports selecting a deployed model, uploading a CSV, previewing results, and downloading a CSV with predictions.

## Implementation progress

| Milestone | Status | Current scope |
| --- | --- | --- |
| v0.1 Prediction Server | Completed | Model selection, CSV prediction, missing-row cleanup, optional Ground Truth evaluation, metrics, preview, and download |
| v0.2 Prediction History | Completed | Stateless prediction metadata history with injectable repository storage |
| v0.3 Classification and training controls | In progress | Classification training and Logistic Regression are implemented; Ridge and richer model controls remain planned |
| v0.4 Explainability | Deferred | SHAP-backed explainability and prediction insights |
| v0.5 Model Registry | Completed | Trusted model registry with publish, enable, disable, and unregister lifecycle controls |
| v0.7.1 Observability | Completed | Health endpoints, request logging, and Prometheus metrics |
| v0.7.2 Queue Workers | Completed | Redis-backed asynchronous training worker with Docker end-to-end verification |

The latest Prediction update rounds regression `prediction` and `prediction_error` values to four decimal places in the returned CSV. Full-precision values remain in the evaluation calculations. Long prediction-preview headers and cell values expose tooltips so Chinese and long feature names remain readable.

## v0.1 completed

- Model discovery from `backend/ml_models/`
- CSV batch prediction for trusted sklearn artifacts
- Optional Ground Truth scoring during prediction (regression metrics and row-level errors)
- Prediction preview keeps compact columns and provides tooltips for full headers and values
- Stateless API: prediction results are returned directly as CSV
- Vue 3 interface with upload, preview, and download
- Dataset upload and profile pages with Chinese CSV encoding support
- Regression training for Random Forest, Gradient Boosting, XGBoost, and AdaBoost
- Draft-to-published model workflow; published models appear in Prediction automatically
- Dataset and trained-model display-name editing without changing original CSV filenames
- Traditional Chinese / English UI switching with a persisted language preference
- Background training progress and optional Random Forest, Gradient Boosting, and XGBoost hyperparameter overrides
- Docker Compose deployment

## v0.2 completed

- Successful prediction metadata is recorded through an injectable `PredictionHistoryRepository`.
- `GET /api/prediction-history` returns prediction history in reverse chronological order.
- The initial file adapter persists metadata only; uploaded CSV files and prediction outputs are not retained.
- The frontend provides Traditional Chinese / English switching with a persisted language preference.
- Prediction, history, dataset, training, and trained-model pages share a responsive visual design system.
- Tables support compact layouts, readable typography, and full-value hover tooltips for truncated content.

## v0.3 in progress

- Classification training with stratified cross-validation and classification metrics is implemented for Random Forest, Gradient Boosting, XGBoost, AdaBoost, and Logistic Regression.
- Ridge regression and richer regularized linear-model controls remain planned for the standalone AutoML platform.
- Keep regression and classification model manifests compatible with the existing trained-model and prediction workflows.

## v0.5 completed

- Replace runtime folder scanning with a file-backed model registry while keeping `ModelCatalog` as the Prediction application boundary.
- Add a Model Registry page for viewing, enabling, disabling, and unregistering trusted model packages.
- Refine the registry table with compact responsive columns, clear status badges, action buttons, and hover details for truncated values.
- Published model artifacts remain operator-controlled files; registry removal never accepts or deletes serialized artifacts through HTTP.

## v0.7.1 completed

- Structured JSON request and training-job logs with request IDs.
- Liveness/readiness endpoints at `/health/live` and `/health/ready`.
- Prometheus metrics at `/metrics` for HTTP requests, predictions, and training jobs.

## v0.7.2 completed

- Replace local background jobs with a Redis-backed training queue and independent worker.
- Keep the existing training-job polling API stable while jobs run asynchronously.
- Verify the complete Docker Compose training flow end to end, including persisted job records and trained artifacts.

## Future roadmap

- v0.7.2 follow-up: add retry/dead-letter handling and graceful worker shutdown.
- v0.7.3: add queue operations, worker capacity controls, and queue-depth monitoring.
- v0.8: add a frontend observability dashboard for API health, registry availability, training activity, prediction outcomes, and operational errors.

## Quick start

```bash
docker compose up --build
```

Open http://localhost:5173. The API is available at http://localhost:8000 and its OpenAPI UI at http://localhost:8000/docs.

The Docker Compose setup runs the complete v0.7.2 workflow:

- `frontend`: Vue application served by Nginx.
- `backend`: FastAPI API server.
- `redis`: training job queue.
- `worker`: independent training worker.

Training jobs flow from the API to Redis and are executed by the worker. The backend and worker share the persistent data volume for datasets, job records, and trained artifacts.

## Windows development launchers

After completing the one-time local setup below, choose the launcher that matches the workflow:

Prediction-only (FastAPI + frontend, no Redis or training worker):

```powershell
.\start-dev.bat
```

Full local training workflow (Docker Redis + FastAPI + frontend + local training worker):

```powershell
.\start-dev-redis.bat
```

`start-dev-redis.bat` starts only the Redis container through Docker Compose, then calls `start-dev.bat` and opens a separate training-worker terminal. It automatically uses `backend/.venv` when present, falling back to `backend/.venv-local`. Docker Desktop must be running before using this launcher.

Three deterministic example model packages are included:

| Model | Task | Sample CSV |
| --- | --- | --- |
| HousePrice | Regression | `backend/sample_data/house_price_input.csv` |
| CreditRisk | Binary classification | `backend/sample_data/credit_risk_input.csv` |
| CustomerChurn | Binary classification | `backend/sample_data/customer_churn_input.csv` |

## Local development

The asynchronous training API uses Redis by default. You can run the complete stack with Docker Compose, or run the API and frontend locally while using Docker only for Redis and the worker.

For the hybrid local workflow, Redis can be started manually:

```powershell
docker compose up -d redis
```

Alternatively, use `start-dev-redis.bat` from the project root to start Redis, Backend, Frontend, and the local worker together.

Then run the FastAPI server in one terminal:

```powershell
cd backend
python -m venv .venv
# Windows: If multiple Python versions are installed, explicitly select Python 3.12:
# py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/build_example_models.py
uvicorn app.main:app --reload
```

Run the training worker in a second backend terminal when using the manual workflow:

```powershell
cd backend
.venv\Scripts\activate
python -m app.workers.training_worker
```

If only the FastAPI server is started without Redis and the worker, Prediction remains available but `POST /api/training/jobs` cannot enqueue work and returns `503 Training queue is unavailable`.

```bash
cd frontend
npm install
npm run dev
```

When updating an existing local environment after pulling the training module, run `pip install -r requirements.txt` again. It installs XGBoost in addition to the original prediction dependencies.

## Training workflow

1. Upload a CSV in **數據集管理**, inspect columns, and optionally rename its display name.
2. In **模型訓練**, choose one numeric target and check the feature columns to use.
3. Select an algorithm. Random Forest exposes tree-count and split/leaf controls; Gradient Boosting exposes `n_estimators` and `learning_rate`; XGBoost exposes its optional hyperparameter fields. Logistic Regression exposes `penalty`, `solver`, and `C` for classification. Leaving fields empty uses the estimator defaults.
4. Review the background-job progress, then inspect the Draft model metrics.
5. Publish the model to make it available in **Prediction**.

## Documentation

See [docs/01_Project.md](docs/01_Project.md) for the roadmap and [docs/04_Architecture.md](docs/04_Architecture.md) for the design.
See [DEVELOPMENT_MEMO.md](DEVELOPMENT_MEMO.md) for the local development, Docker verification, and Git workflow.
