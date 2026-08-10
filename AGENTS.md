# EdgeML Agent Guide

## Product scope

EdgeML is an enterprise-oriented, self-hosted machine-learning prediction platform. The focused regression-training workflow is integrated only during the early milestones to validate the end-to-end experience; the long-term architecture will move training into a standalone AutoML platform. Work incrementally: v0.1 includes dataset profiling, regression training and evaluation, draft-to-published model lifecycle, and stateless batch prediction. Preserve boundaries that allow training to be extracted later. Do not add databases, authentication, model uploading, SHAP, monitoring, classification training, or production orchestration unless the active milestone requires them.

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

