# Database

EdgeML currently has no database. Prediction outputs remain stateless and are returned directly to the caller.

v0.2 introduces prediction-history metadata behind the `PredictionHistoryRepository` abstraction. The initial adapter appends JSON Lines records to `backend/data/prediction_history.jsonl`; Docker Compose stores this path in a named volume. CSV inputs and prediction outputs are never persisted by the history repository. A future database adapter can replace the file implementation without changing `PredictionService`.

The first Training Module uses local filesystem persistence to avoid prematurely adding database infrastructure:

- `backend/data/datasets/`: trusted uploaded CSVs and dataset-profile metadata.
- `backend/trained_models/`: draft training artifacts and training records.
- `backend/ml_models/`: published artifact packages referenced by the Prediction Server's model registry.
- `backend/data/model_registry.json`: the v0.5 file-backed registry index for trusted published model packages and their active/disabled status.
- Configured `training_jobs_root` (Docker: `/app/data/training_jobs`): shared JSON job records consumed by the API and queue workers.

Multi-user prediction and training may introduce database persistence behind the existing repository boundary in a later milestone. Database selection and schema will be decided then.
