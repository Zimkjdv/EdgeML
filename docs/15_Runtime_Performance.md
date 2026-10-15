# Runtime cache and bounded dataset profiling

## Guarantees and limits (R25)

The Backend composes a per-process LRU `CachedPredictorProvider` behind the existing `PredictorProvider`/`BasePredictor` boundary. Prediction still resolves the active Registry entry on every request; the cache is never an authentication/catalog authority. Optimization and importance recomputation use the same provider. No model packages or request/output CSVs are added to persistent storage by the cache.

The key includes canonical model ID, manifest/version, resolved artifact paths and each artifact/preprocessor file's size, mtime, ctime and inode. Changed manifests/files evict the preceding identity; missing artifacts fail rather than returning a retained runtime. Normal local rename/publish/delete/Registry changes also invalidate that process's runtime. Other processes observe Registry and file changes on their next request. Requests already accepted before a lifecycle change may finish; this is not cancellation of in-flight inference.

The stat signature is a change detector, not a cryptographic integrity check. Trusted deployments must replace artifacts atomically and/or increment the version; deliberately editing in place while preserving timestamps is not a supported hot-update protocol. Application/plugin code changes require a process restart. Serialized artifacts remain trusted deployment inputs, never HTTP uploads.

Concurrent first requests share one load. Unrelated loads have bounded admission, and loading never holds the global LRU lock. Failed/interrupted loads are not retained; file changes during loading reject the result, with no stale fallback. A per-runtime lock serializes predict/proba/explain so plugins need not promise thread-safe transformers. Eviction removes only the cache reference: accepted requests keep their own references until completion.

| Environment setting | Default | Meaning |
| --- | --- | --- |
| `EDGEML_MODEL_CACHE_ENTRIES` | 4 | Maximum retained runtimes per Backend process; 0 disables caching |
| `EDGEML_MODEL_CACHE_ARTIFACT_BYTES` | 268435456 | Maximum sum of retained artifact disk sizes; oversized models run without retention |
| `EDGEML_MODEL_CACHE_LOAD_CONCURRENCY` | 2 | Maximum simultaneous cold loads; overload returns 503 |
| `EDGEML_DATASET_PROFILE_CONCURRENCY` | 2 | Maximum accepted/running CSV profiling tasks per application |

Artifact bytes are **not an RSS limit**: decompressed arrays/estimators may use substantially more RAM. Multiple Backend processes multiply cache/resource budgets. In-flight work can temporarily keep evicted models alive. Settings are typed and Compose forwards them; export them explicitly for local processes if your launcher does not load optional variables. No production Docker deployment is performed by tests or Git publication.

Dataset upload parsing/profiling/storage runs on a dedicated bounded thread pool, not the ASGI event loop or the shared synchronous-route thread pool. Capacity exhaustion returns `503` and `Retry-After: 1` before invoking `DatasetService.upload`; there is no unbounded profiling-job queue. Existing file-size/CSV syntax/transaction validation is preserved. Multipart parsing/network buffers remain subject to the existing HTTP/server limits, not this CPU pool's admission limit.

Client cancellation does not stop an already running profiling thread and does not free its slot early. Accepted work may still create a dataset after disconnect: check the dataset list before blindly resubmitting. Shutdown rejects new work and lets running bounded tasks finish. This is not a new durable profiling job system.

## Reproducible measurement

Run from `backend` with the project's Python environment:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_prediction_cache.py --iterations 30
```

Use `.venv-local` in the path if that is your environment's name. The script trains a synthetic Random Forest in a temporary directory, runs uncached/cached modes in separate child processes, checks identical predictions, and removes its temporary data. It never reads production models, DBs, tokens or network services.

2026-10-15 Windows / Python 3.12.10, 120 trees, 1,600 training rows, eight features, 16 prediction rows, 15,224,049-byte artifact, 30 measured iterations after the first request:

| Mode | First runtime load + prediction (ms) | Steady p50 (ms) | Steady p95 (ms) | Baseline RSS (bytes) | Final RSS (bytes) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Uncached | 220.921 | 172.434 | 249.531 | 153722880 | 156827648 |
| Cached | 165.122 | 86.921 | 126.984 | 153739264 | 173162496 |

These are **direct PredictionService** measurements, not HTTP throughput or production capacity; they exclude network/authentication/disk-history costs and include tracemalloc overhead. The OS filesystem cache is not flushed, so “first” means cold runtime, not cold physical disk. Observed RSS maxima were 160333824/173096960 bytes, Python-traced peaks 16164552/15875392 bytes. The cache retains more resident memory in this example; do not claim memory savings or extrapolate latency to other models/hardware/workloads. Re-run to size a deployment.

Tests exercise single-flight loads, per-runtime serialization, LRU/byte limits, missing/replaced artifacts/preprocessors, metadata/version changes, failure retry, invalidation during loading, disabled/deleted Registry entries, bounded load overload, cancellation admission and health responses during blocked profiling. Full multi-user capacity/readiness/metrics work remains on ROADMAP.
