# Future design

The authoritative ordered reliability backlog is [ROADMAP.md](../ROADMAP.md), including the complete 2026-09-21 project review, implemented fixes, acceptance criteria, and remaining items. Product milestones below remain the longer-term direction.

- **v0.2:** inject a history repository into `PredictionService` and persist durable training-job metadata.
- **v0.3 (in progress):** classification training with stratified evaluation and classification metrics is implemented for Random Forest, Gradient Boosting, XGBoost, AdaBoost, and Logistic Regression with configurable penalty, solver, and C. Ridge, Lasso Lars, Stacking, and richer feature-dimension reduction controls remain planned follow-up work.
- **v0.4 (deferred):** add SHAP-backed `explain` support through predictor capabilities.
- **v0.5 (completed):** replace runtime folder scanning with a file-backed model registry while keeping `ModelCatalog` as the application boundary. Add registry status controls and a responsive Model Registry management page with compact columns, status badges, and clear lifecycle actions.
- **v0.6 (in progress):** add SQLite-backed API token generation, scoped access, one-time token display, listing, and revocation. Keep `EDGEML_API_TOKEN` as the bootstrap management token and use a reverse proxy for stronger production authentication.
- **v0.7.1 (completed):** add structured JSON logs, request IDs, Prometheus metrics, and liveness/readiness checks without changing the existing training API.
- **v0.7.2 (completed):** replace local background jobs with a Redis-backed queue/worker system for long-running concurrent training while keeping the job polling API stable. The Docker runtime flow is verified end to end.
- **v0.7.3 (in progress):** bounded retries with configurable attempt limits, exponential backoff, dead-letter routing, graceful worker shutdown, backend Queue Operations APIs, an auto-refreshing Queue Operations UI, and Docker worker replica scaling documentation are implemented. Runtime integration tests remain planned.
- **v0.8 (planned):** add a frontend observability dashboard for API health, registry availability, training-job activity, prediction outcomes, and recent operational errors. The dashboard will consume read-only monitoring APIs and will not expose raw logs or uploaded data by default.
- **Reliability backlog:** Redis persistence, shared-volume worker recovery, durable published packages and Registry transactions are implemented. Remaining JSON transactions, dead-letter replay consistency, stronger input limits, broader runtime integration, finer token scopes and backup/restore are tracked in ROADMAP. Use a reverse proxy or external identity provider for production authentication.
- **v1.0:** extract the early integrated training workflow into a standalone AutoML platform with production orchestration and experiment tracking. EdgeML will consume published model packages and remain focused on deployment and prediction.

## Product boundary

### Parameter optimization

Implemented initial scope: bilingual simulation page, one trained or active registered regression model, numeric target and tolerance, fixed features, bounded numeric/step search, allowed category choices, seeded search, and up to five distinct recommendations with prediction/error comparison. See [Parameter optimization](07_Parameter_Optimization.md).

Training-data ranges and median/mode fixed defaults are implemented, with metadata snapshots for new models and source-dataset lookup for older models. Planned extensions: multiple weighted objectives, target intervals and classification targets, cross-feature process constraints, anomaly penalties, configurable diversity, calibrated uncertainty, persisted simulations, CSV export, and queued/cancellable execution with concurrency limits.

Training is intentionally integrated during the early milestones so the end-to-end workflow can be developed and validated quickly. This is a transitional architecture, not the final service boundary. The future AutoML platform will own datasets, experiments, training jobs, evaluation, and model publication; EdgeML will own the deployed model catalog, prediction validation, and prediction serving.
