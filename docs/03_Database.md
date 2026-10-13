# Database

Training output is assembled under `.staging-<model-id>-<attempt-id>` and becomes visible only after an atomic directory rename. Job output IDs are reserved before fitting. `output_commit` stores job ownership, request hash, and streaming SHA256 of model.pkl; recovery verifies it and only confirms the existing result. Interrupted staging is moved to `.abandoned-*` for diagnostics and excluded from all model catalogs. Completed pre-upgrade jobs keep their original IDs; unassociated legacy orphan artifacts require operator review, not automatic matching/deletion.

Prediction outputs remain stateless and are returned directly to the caller. Model, dataset and job records use files; API-token and browser-session metadata use the existing SQLite authentication database.

v0.2 introduces prediction-history metadata behind the `PredictionHistoryRepository` abstraction. The initial adapter appends JSON Lines records to `backend/data/prediction_history.jsonl`; Docker Compose stores this path in a named volume. CSV inputs and prediction outputs are never persisted by the history repository. A future database adapter can replace the file implementation without changing `PredictionService`.

The first Training Module uses local filesystem persistence to avoid prematurely adding database infrastructure:

- `backend/data/datasets/`: trusted uploaded CSVs and dataset-profile metadata.
- `backend/trained_models/`: draft training artifacts and training records.
- `backend/ml_models/` locally, `/app/data/published_models` in Docker: published artifact packages referenced by the Prediction Server's model registry. Docker packages share the persistent data Volume with Registry metadata; the image's `/app/ml_models` only seeds missing packages. New publications use model-ID folder names.

Registry JSON mutations are serialized across processes with an OS file lock and atomic replacement. Worker ownership lock files reside under the common training-jobs directory; their presence alone does not indicate a live owner (the kernel-held lock does). Never delete active lock files. Other JSON state files still need the transaction work listed in [ROADMAP](../ROADMAP.md).

Trained-model evaluate/rename/publish/delete operations also share an OS lock per model in `trained_models/.locks/`, outside deletable model folders. Operations involving publication acquire the publication lock before the per-model lock; evaluation uses only its model lock so different models can evaluate concurrently. Record and manifest JSON use flush/fsync plus atomic replacement. New models expose `record.json` last, after artifacts are complete. Locks serialize live operations; they are not a multi-file crash-recovery transaction. Dataset/job/history transaction details follow below; model artifact/job output recovery uses the commit protocol below.

Job JSON writes use unique temporary files, flush/fsync and atomic replacement. Short per-job OS state locks serialize read-modify-write; a separate execution lock excludes overlapping runs while polling remains available. `.dispatch-<job-id>.txn` is an outbox marker written before job creation and removed after successful dispatch/reconciliation. Workers recover marked queued jobs, including after lost Redis replies. Cancellation persists terminal intent before Redis removal, and stale progress/enqueue errors cannot revive terminal or active jobs. A reserved output_model_id and output_commit (job ID, request SHA256, artifact SHA256) link model output to job completion.

Datasets share `.datasets.lock` across processes. Upload/delete intent uses `.upload-<uuid>.txn` / `.delete-<uuid>.txn`; CSV is flushed before publishing atomic metadata. The next operation under the lock rolls back interrupted uploads without metadata, retains completed uploads, and completes prepared deletes. Only marked transactions are recovered; unrelated orphan files are not deleted. Rename is atomic, and complete CSV reads serialize with deletion. Hidden operational locks/markers are not datasets.

History appends are flushed under a cross-process lock. Pagination uses bounded in-memory selection; scanning remains linear in the active file size. Corruption repair and opt-in retention archive original bytes before atomically replacing the active log. Retention defaults to unlimited; archived files are retained for operator recovery/cleanup. Dataset/job/history guarantees apply to participants sharing the same single-host local filesystem, not unverified NFS/SMB or independent host disks.
- `backend/data/model_registry.json`: the v0.5 file-backed registry index for trusted published model packages and their active/disabled status.
- Configured `training_jobs_root` (Docker: `/app/data/training_jobs`): shared JSON job records consumed by the API and queue workers.

Multi-user prediction and training may introduce database persistence behind the existing repository boundary in a later milestone. Database selection and schema will be decided then.
