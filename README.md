# EdgeML

Enterprise Edge Machine Learning Prediction Platform.

EdgeML is a self-hosted, plugin-oriented platform for batch predictions from CSV files. Its first milestone supports selecting a deployed model, uploading a CSV, previewing results, and downloading a CSV with predictions.

## v0.1 capabilities

- Model discovery from `backend/ml_models/`
- CSV batch prediction for trusted sklearn artifacts
- Stateless API: prediction results are returned directly as CSV
- Vue 3 interface with upload, preview, and download
- Dataset upload and profile pages with Chinese CSV encoding support
- Regression training for Random Forest, Gradient Boosting, XGBoost, and AdaBoost
- Draft-to-published model workflow; published models appear in Prediction automatically
- Dataset and trained-model display-name editing without changing original CSV filenames
- Traditional Chinese / English UI switching with a persisted language preference
- Background training progress and optional XGBoost hyperparameter overrides
- Docker Compose deployment

## v0.2 current status

- Successful prediction metadata is recorded through an injectable `PredictionHistoryRepository`.
- `GET /api/prediction-history` returns prediction history in reverse chronological order.
- The initial file adapter persists metadata only; uploaded CSV files and prediction outputs are not retained.
- The frontend provides Traditional Chinese / English switching with a persisted language preference.
- Prediction, history, dataset, training, and trained-model pages share a responsive visual design system.
- Tables support compact layouts, readable typography, and full-value hover tooltips for truncated content.

## v0.3 in progress

- Add classification training with stratified cross-validation and classification metrics.
- Add Ridge regression as a regularized linear baseline.
- Keep regression and classification model manifests compatible with the existing trained-model and prediction workflows.

## v0.5 completed

- Replace runtime folder scanning with a file-backed model registry while keeping `ModelCatalog` as the Prediction application boundary.
- Add a Model Registry page for viewing, enabling, disabling, and unregistering trusted model packages.
- Published model artifacts remain operator-controlled files; registry removal never accepts or deletes serialized artifacts through HTTP.

## v0.7.1 in progress

- Structured JSON request and training-job logs with request IDs.
- Liveness/readiness endpoints at `/health/live` and `/health/ready`.
- Prometheus metrics at `/metrics` for HTTP requests, predictions, and training jobs.

## Future roadmap

- v0.7.2: replace local background jobs with queue-backed training workers.
- v0.8: add a frontend observability dashboard for API health, registry availability, training activity, prediction outcomes, and operational errors.

## Quick start

```bash
docker compose up --build
```

Open http://localhost:5173. The API is available at http://localhost:8000 and its OpenAPI UI at http://localhost:8000/docs.

## Windows development launcher

After completing the one-time local setup below, double-click `start-dev.bat` in the project root, or run it from PowerShell:

```powershell
.\start-dev.bat
```

It opens separate terminals for the FastAPI reload server and Vite development server. It automatically uses `backend/.venv` when present, falling back to `backend/.venv-local`.

Three deterministic example model packages are included:

| Model | Task | Sample CSV |
| --- | --- | --- |
| HousePrice | Regression | `backend/sample_data/house_price_input.csv` |
| CreditRisk | Binary classification | `backend/sample_data/credit_risk_input.csv` |
| CustomerChurn | Binary classification | `backend/sample_data/customer_churn_input.csv` |

## Local development

```bash
cd backend
python -m venv .venv
# Windows: If multiple Python versions are installed, explicitly select Python 3.12:
# py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/build_example_models.py
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

When updating an existing local environment after pulling the training module, run `pip install -r requirements.txt` again. It installs XGBoost in addition to the original prediction dependencies.

## Training workflow

1. Upload a CSV in **數據集管理**, inspect columns, and optionally rename its display name.
2. In **模型訓練**, choose one numeric target and check the feature columns to use.
3. Select a regression algorithm. XGBoost exposes optional hyperparameter fields; leaving them empty uses native XGBoost defaults.
4. Review the background-job progress, then inspect the Draft model metrics.
5. Publish the model to make it available in **Prediction**.

## Documentation

See [docs/01_Project.md](docs/01_Project.md) for the roadmap and [docs/04_Architecture.md](docs/04_Architecture.md) for the design.
