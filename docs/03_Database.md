# Database

v0.1 prediction intentionally has no database. Requests are stateless and prediction outputs are returned directly to the caller.

The first Training Module uses local filesystem persistence to avoid prematurely adding database infrastructure:

- `backend/data/datasets/`: trusted uploaded CSVs and dataset-profile metadata.
- `backend/trained_models/`: draft training artifacts and training records.
- `backend/ml_models/`: published artifact packages scanned by the Prediction Server.

Prediction history and multi-user training will introduce database persistence behind repository abstractions in a later milestone. Database selection and schema will be decided then.
