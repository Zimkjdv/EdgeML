# EdgeML

Enterprise Edge Machine Learning Prediction Platform.

EdgeML is a self-hosted, plugin-oriented platform for batch predictions from CSV files. Its first milestone supports selecting a deployed model, uploading a CSV, previewing results, and downloading a CSV with predictions.

## v0.1 capabilities

- Model discovery from `backend/ml_models/`
- CSV batch prediction for trusted sklearn artifacts
- Stateless API: prediction results are returned directly as CSV
- Vue 3 interface with upload, preview, and download
- Docker Compose deployment

## Quick start

```bash
docker compose up --build
```

Open http://localhost:5173. The API is available at http://localhost:8000 and its OpenAPI UI at http://localhost:8000/docs.

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

## Documentation

See [docs/01_Project.md](docs/01_Project.md) for the roadmap and [docs/04_Architecture.md](docs/04_Architecture.md) for the design.
