# EdgeML Agent Guide

## Product scope

EdgeML is an enterprise-oriented, self-hosted machine-learning prediction platform. Work incrementally: v0.1 is prediction only. Do not add databases, authentication, model uploading, SHAP, monitoring, or training features unless the active milestone requires them.

## Required stack

- Backend: FastAPI and Python.
- Frontend: Vue 3, Vite, and Element Plus.
- Deployment: Docker Compose.

## Architecture rules

- Routers only translate HTTP requests and responses. Business logic belongs in services.
- Depend on abstractions; do not import framework-specific predictors in routers or services.
- Every model runtime implements `BasePredictor`.
- Model folders are discovered by the model catalog. Never hard-code a model name in an API route.
- All settings come from typed configuration, model manifests, or environment variables.
- Prediction APIs are stateless. Return the generated CSV directly; the frontend owns its preview and download.

## Quality and security

- Keep `docker compose up --build` runnable.
- Add or update tests for behavioral changes.
- Update `README.md` and the relevant file in `docs/` for user-facing or architectural changes.
- Serialized model artifacts are trusted deployment inputs only. Never accept an uploaded pickle/joblib file.
- Never install a model folder's `requirements.txt` at runtime.
- Validate CSV size, headers, feature types, and model identifiers before prediction.

