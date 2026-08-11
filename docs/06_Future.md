# Future design

- **v0.2:** inject a history repository into `PredictionService` and persist durable training-job metadata.
- **v0.3 (in progress):** classification training with stratified evaluation and classification metrics is implemented for Random Forest, Gradient Boosting, XGBoost, AdaBoost, and Logistic Regression with configurable penalty, solver, and C. Ridge, Lasso Lars, Stacking, and richer feature-dimension reduction controls remain planned follow-up work.
- **v0.4 (deferred):** add SHAP-backed `explain` support through predictor capabilities.
- **v0.5 (completed):** replace runtime folder scanning with a file-backed model registry while keeping `ModelCatalog` as the application boundary. Add registry status controls and a responsive Model Registry management page with compact columns, status badges, and clear lifecycle actions.
- **v0.6:** add API-token authentication middleware and access-control boundaries.
- **v0.7.1 (completed):** add structured JSON logs, request IDs, Prometheus metrics, and liveness/readiness checks without changing the existing training API.
- **v0.7.2 (completed):** replace local background jobs with a Redis-backed queue/worker system for long-running concurrent training while keeping the job polling API stable. The Docker runtime flow is verified end to end.
- **v0.7.3 (in progress):** bounded retries with configurable attempt limits, exponential backoff, dead-letter routing, graceful worker shutdown, backend Queue Operations APIs, an auto-refreshing Queue Operations UI, and Docker worker replica scaling documentation are implemented. Runtime integration tests remain planned.
- **v0.8 (planned):** add a frontend observability dashboard for API health, registry availability, training-job activity, prediction outcomes, and recent operational errors. The dashboard will consume read-only monitoring APIs and will not expose raw logs or uploaded data by default.
- **v1.0:** extract the early integrated training workflow into a standalone AutoML platform with production orchestration and experiment tracking. EdgeML will consume published model packages and remain focused on deployment and prediction.

## Product boundary

Training is intentionally integrated during the early milestones so the end-to-end workflow can be developed and validated quickly. This is a transitional architecture, not the final service boundary. The future AutoML platform will own datasets, experiments, training jobs, evaluation, and model publication; EdgeML will own the deployed model catalog, prediction validation, and prediction serving.
