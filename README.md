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
| v0.7.3 Queue Operations | In progress | Backend retry, dead-letter routing, graceful shutdown, queue-control APIs, Queue Operations UI, and worker-capacity controls; runtime integration coverage remains next |

The latest Prediction update rounds regression `prediction` and `prediction_error` values to four decimal places in the returned CSV. Full-precision values remain in the evaluation calculations. Long prediction-preview headers and cell values expose tooltips so Chinese and long feature names remain readable.

Prediction clients can use either `POST /api/predict` for CSV upload/download or `POST /api/predict/json` for direct JSON `data` from a database or service integration. The JSON endpoint returns prediction records and evaluation metadata without creating a temporary CSV file.

`predict_api_example.py` also includes `get_model_id_by_name("HousePrice")`, a requests-based example of calling `GET /api/models/by-name/{model_name}` before submitting a JSON prediction.

For integrations that need to discover models, use `GET /api/models/ids` to retrieve all active model IDs, or `GET /api/models/by-name/{model_name}` to resolve a display name such as `HousePrice` to its stable model ID. The ID-list endpoint returns a JSON array such as `["house-price-v1", "credit-risk-v1"]`, which can be used to populate a client-side model selector. The `by-name` segment intentionally uses kebab-case for a readable and consistent URL; keep this path unchanged in clients.

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

## v0.7.3 in progress

- Backend reliability controls for bounded retry, dead-letter routing, and graceful worker shutdown are implemented.
- Queue Operations APIs now expose queue depths, dead-letter metadata, manual requeue, and cancellation of queued jobs.
- The frontend now includes a Queue Operations page for queue depth, queued/processing IDs, retry attempts, dead-letter inspection, requeue, and cancellation.
- Queue Operations refreshes automatically and supports running multiple Docker worker replicas against the shared Redis queue.
- Windows launchers now cover the hybrid Redis/local workflow, full Docker startup, and rebuild/deploy flows; the hybrid launcher skips Redis startup when the Redis container is already running.
- Remaining v0.7.3 work is runtime integration coverage and richer capacity controls.

## Future roadmap

- v0.7.3 in progress: bounded retries, exponential backoff, dead-letter routing, graceful worker shutdown, Queue Operations APIs, Queue Operations UI, and worker replica guidance are implemented.
- v0.7.3 follow-up: add runtime integration tests and richer worker-capacity controls.
- v0.8: add a frontend observability dashboard for API health, registry availability, training activity, prediction outcomes, and operational errors.

## Quick start

```bash
docker compose up --build
```

Open the Docker frontend at http://localhost:5180. The Docker API is available at http://localhost:8010 and its OpenAPI UI at http://localhost:8010/docs. These are host mappings; containers continue to use Backend `8000`, Frontend `80`, and Redis `6379` internally.

The Docker Compose setup runs the complete v0.7.2 workflow:

- `frontend`: Vue application served by Nginx.
- `backend`: FastAPI API server.
- `redis`: training job queue.
- `worker`: independent training worker.

Training jobs flow from the API to Redis and are executed by the worker. The backend and worker share the persistent data volume for datasets, job records, and trained artifacts.

To increase training capacity, run multiple worker replicas while keeping a single API and Redis instance:

```bash
docker compose up -d --build --scale worker=3
```

Each worker consumes the same Redis-backed queue. The Queue Operations page shows the combined queue state; use `docker compose ps worker` to inspect the worker replicas.

## JSON prediction API example

`POST /api/predict/json` accepts records from a database or another service and returns JSON. The request uses `data` as the input array:

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

For a runnable Python client, install `requests` in the environment where the script runs and execute:

```powershell
python -m pip install requests
python predict_api_example.py
```

The response includes `model_name`, `prediction_column`, a `records` array containing predictions, optional evaluation `metrics`, and `dropped_rows`. The legacy `records` request field is still accepted for compatibility, but new integrations should send `data`.

## Windows development launchers

### First-time setup on a new Windows computer

Install Git, Python 3.12, Node.js LTS, and Docker Desktop first. Then run the following commands from PowerShell:

```powershell
git clone https://github.com/Zimkjdv/EdgeML.git
cd EdgeML

cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Optional: rebuild the deterministic example model packages.
.\.venv\Scripts\python.exe scripts/build_example_models.py

cd ..\frontend
npm.cmd install

cd ..
```

Start Docker Desktop before launching the hybrid environment. The launcher automatically starts the isolated Redis container, applies `EDGEML_REDIS_URL=redis://localhost:6381/0`, and uses the local `.venv` for Backend and Worker:

```powershell
.\start-dev-redis.bat
```

The first-time setup is only required once per computer. Later starts only need `.\start-dev-redis.bat`.

### First full Docker start

The full Docker runtime does not require a local Python virtual environment or frontend `node_modules`; Docker builds those dependencies inside the images. After Docker Desktop is running, perform the first build and start with:

```powershell
.\deploy-docker.bat
```

This builds and starts Backend, Frontend, Redis, and Worker. The Docker endpoints are:

```text
Frontend: http://localhost:5180
API docs: http://localhost:8010/docs
Redis:    localhost:6380
```

After the images have been built, use `.\start-dev-docker.bat` for subsequent starts without rebuilding. If you specifically want to use `start-dev-docker.bat` the first time, run `docker compose build` once beforehand.

After completing the one-time local setup below, choose the launcher that matches the workflow:

Prediction-only (FastAPI + frontend, no Redis or training worker):

```powershell
.\start-dev.bat
```

Full local training workflow (Docker Redis + FastAPI + frontend + local training worker):

```powershell
.\start-dev-redis.bat
```

`start-dev-redis.bat` starts an isolated hybrid Redis container on host port `6381`, then calls `start-dev.bat` and opens a separate training-worker terminal. The local Backend and Worker inherit `EDGEML_REDIS_URL=redis://localhost:6381/0`. It automatically uses `backend/.venv` when present, falling back to `backend/.venv-local`. Docker Desktop must be running before using this launcher.

Full Docker runtime (Backend, Frontend, Redis, and Worker):

```powershell
.\start-dev-docker.bat
```

The Docker launcher starts existing images without rebuilding. You can pass a worker replica count, for example `.\start-dev-docker.bat 2`.

After local development and testing are complete, rebuild and deploy the whole project with:

```powershell
.\deploy-docker.bat
```

This runs `docker compose up -d --build --remove-orphans`. Pass a worker replica count when needed, for example `.\deploy-docker.bat 2`. The full Docker runtime uses host ports `8010` (API), `5180` (Frontend), and `6380` (Redis), so it can run beside the hybrid launcher, which uses local `8000`／`5173` and isolated Redis `6381`.

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
docker compose -p edgeml-hybrid-redis -f docker-compose.hybrid-redis.yml up -d redis
$env:EDGEML_REDIS_URL = "redis://localhost:6381/0"
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
