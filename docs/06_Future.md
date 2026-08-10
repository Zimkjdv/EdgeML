# Future design

- **v0.2:** inject a history repository into `PredictionService` and persist durable training-job metadata.
- **v0.3 (in progress):** add classification training with stratified evaluation and classification metrics, plus Ridge regression as a regularized baseline. Lasso Lars, Stacking, and richer feature-dimension reduction controls remain planned follow-up work.
- **v0.4:** add SHAP-backed `explain` support through predictor capabilities.
- **v0.5:** replace the file-only catalog with a model registry while keeping `ModelCatalog` as the application boundary.
- **v0.6:** add API-token authentication middleware and access-control boundaries.
- **v0.7:** add structured logs, metrics, and health checks, and replace local background jobs with a queue/worker system for long-running concurrent training.
- **v1.0:** extract the early integrated training workflow into a standalone AutoML platform with production orchestration and experiment tracking. EdgeML will consume published model packages and remain focused on deployment and prediction.

## Product boundary

Training is intentionally integrated during the early milestones so the end-to-end workflow can be developed and validated quickly. This is a transitional architecture, not the final service boundary. The future AutoML platform will own datasets, experiments, training jobs, evaluation, and model publication; EdgeML will own the deployed model catalog, prediction validation, and prediction serving.
