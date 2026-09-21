# Database

Prediction outputs remain stateless and are returned directly to the caller. Model, dataset and job records use files; API-token and browser-session metadata use the existing SQLite authentication database.

v0.2 introduces prediction-history metadata behind the `PredictionHistoryRepository` abstraction. The initial adapter appends JSON Lines records to `backend/data/prediction_history.jsonl`; Docker Compose stores this path in a named volume. CSV inputs and prediction outputs are never persisted by the history repository. A future database adapter can replace the file implementation without changing `PredictionService`.

The first Training Module uses local filesystem persistence to avoid prematurely adding database infrastructure:

- `backend/data/datasets/`: trusted uploaded CSVs and dataset-profile metadata.
- `backend/trained_models/`: draft training artifacts and training records.
- `backend/ml_models/` locally, `/app/data/published_models` in Docker: published artifact packages referenced by the Prediction Server's model registry. Docker packages share the persistent data Volume with Registry metadata; the image's `/app/ml_models` only seeds missing packages. New publications use model-ID folder names.

Registry JSON mutations are serialized across processes with an OS file lock and atomic replacement. Worker ownership lock files reside under the common training-jobs directory; their presence alone does not indicate a live owner (the kernel-held lock does). Never delete active lock files. Other JSON state files still need the transaction work listed in [ROADMAP](../ROADMAP.md).

Job JSON writes now use a unique temporary file, flush/fsync and atomic replacement. Manual replay persists `replay_pending` before Redis dispatch, allowing an interrupted preparation to be retried without reverting a job that may already be queued. Atomic writes prevent partial-file reads; they do not by themselves serialize every job state transition. The remaining job/dataset/history/model-record transaction work stays under R11.
- `backend/data/model_registry.json`: the v0.5 file-backed registry index for trusted published model packages and their active/disabled status.
- Configured `training_jobs_root` (Docker: `/app/data/training_jobs`): shared JSON job records consumed by the API and queue workers.

Multi-user prediction and training may introduce database persistence behind the existing repository boundary in a later milestone. Database selection and schema will be decided then.
