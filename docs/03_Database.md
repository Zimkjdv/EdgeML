# Database

EdgeML currently has no database. Prediction outputs remain stateless and are returned directly to the caller.

v0.2 introduces prediction-history metadata behind the `PredictionHistoryRepository` abstraction. The initial adapter appends JSON Lines records to `backend/data/prediction_history.jsonl`; Docker Compose stores this path in a named volume. CSV inputs and prediction outputs are never persisted by the history repository. A future database adapter can replace the file implementation without changing `PredictionService`.

The first Training Module uses local filesystem persistence to avoid prematurely adding database infrastructure:

- `backend/data/datasets/`: trusted uploaded CSVs and dataset-profile metadata.
- `backend/trained_models/`: draft training artifacts and training records.
- `backend/ml_models/`: published artifact packages scanned by the Prediction Server.

Multi-user prediction and training may introduce database persistence behind the existing repository boundary in a later milestone. Database selection and schema will be decided then.
