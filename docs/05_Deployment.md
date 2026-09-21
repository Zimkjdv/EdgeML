# Deployment

On Windows, use the deployment launcher so the shared ML base is built before the application images:

```powershell
.\deploy-docker.bat
```

On a fresh installation, if you use Docker Compose directly, build the base image first. For an existing installation, follow the model-storage upgrade below before any recreation:

```powershell
docker build -f backend/Dockerfile.base -t edgeml-ml-base:latest ./backend
docker compose up -d --build
```

`edgeml-ml-base` contains the common Python ML dependencies used by Backend and Worker. It is a Docker build image, not a running container. Backend and Worker retain separate containers while sharing the common image layers. Use `deploy-docker.bat` after cloning or after changing the base dependencies; `start-dev-docker.bat` starts existing images only.

The Docker containers listen internally on Backend port `8000`, Frontend Nginx port `80`, and Redis port `6379`. The default host mappings are Backend `8010`, Frontend `5180`, and Redis `6380`. Set `EDGEML_MODELS_ROOT` to change the deployment model path and `EDGEML_MAX_UPLOAD_BYTES` to limit CSV upload size. Redis uses a named volume with AOF enabled so queued and dead-letter job IDs survive container recreation.

Every service in `docker-compose.yml` and the hybrid Redis compose file uses `restart: unless-stopped`. Docker will restart the service after a daemon or host restart, while an explicit `docker compose stop` or `docker compose down` keeps it stopped until started again.

Configure separate credentials in `.env`: `EDGEML_WEB_USERNAME` / `EDGEML_WEB_PASSWORD` for browser login and `EDGEML_API_TOKEN` for integrations. The frontend no longer embeds API tokens. Browser sessions use HttpOnly cookies and CSRF headers. Existing installs need a web password and a frontend rebuild for this migration. Use HTTPS with `EDGEML_WEB_COOKIE_SECURE=true` for deployed environments, and configure `EDGEML_WEB_ALLOWED_ORIGINS` for the exact public origin. See [Web authentication](10_Web_Authentication.md).

Local development uses different host endpoints:

| Runtime | Frontend | API docs | Redis |
| --- | --- | --- | --- |
| Prediction-only (`start-dev.bat`) | `http://localhost:5173` | `http://localhost:8000/docs` | Not required |
| Hybrid training (`start-dev-redis.bat`) | `http://localhost:5173` | `http://localhost:8000/docs` | `localhost:6381` |
| Full Docker (`start-dev-docker.bat`) | `http://localhost:5180` | `http://localhost:8010/docs` | `localhost:6380` |

Training workers retry transient infrastructure failures with bounded exponential backoff. The defaults are three total attempts, a two-second initial delay, and a 60-second maximum delay. Override them with `EDGEML_TRAINING_MAX_ATTEMPTS`, `EDGEML_TRAINING_RETRY_BACKOFF_SECONDS`, and `EDGEML_TRAINING_RETRY_BACKOFF_MAX_SECONDS`. Deterministic validation and model errors are marked failed without retry; terminal failures are retained in the Redis dead-letter list (`<queue-name>:dead-letter`) for later inspection. On SIGTERM or SIGINT, the worker stops consuming new jobs and exits after the current job lifecycle is finalized.

## Worker capacity

Worker replicas are stateless consumers of the shared Redis queue. Scale them independently from the API and frontend:

```bash
docker compose up -d --build --scale worker=3
docker compose ps worker
```

The Queue Operations page reports the aggregate queued, processing, and dead-letter state. Capacity changes do not require API configuration changes; each replica uses the same Redis URL and persistent job volume.

## Windows local development

For Prediction-only development, run `start-dev.bat` in the repository root after the Python virtual environment and frontend dependencies have been installed. It launches Uvicorn with `--reload` and Vite in separate command windows.

For local development with model training, run `start-dev-redis.bat`. It starts an isolated Docker Redis project on host port `6381`, sets the local `EDGEML_REDIS_URL`, then launches the local Backend on `8000`, Frontend on `5173`, and Training Worker. Docker Desktop must be running. Both launchers prefer `backend/.venv` and fall back to `backend/.venv-local`.

For a complete Docker runtime without rebuilding, run `start-dev-docker.bat`. Whenever local development reaches a stable milestone, use `deploy-docker.bat` to rebuild and deploy the current workspace to the complete Compose project. It is reusable throughout development, not only for the first setup. Both scripts accept an optional worker replica count, such as `deploy-docker.bat 2`; Git commit and push remain separate operations.

The hybrid local launcher and full Docker runtime can run together because they use separate host ports and Redis queues: local `8000`/`5173`/`6381`, Docker `8010`/`5180`/`6380`. Their data directories and worker processes remain independent.

For production, terminate TLS at the organization-approved reverse proxy. Integrated publication requires a writable trusted model store; an inference-only deployment may use read-only artifacts after provisioning.

## Model storage and reliability upgrade

Docker now uses `EDGEML_MODELS_ROOT=/app/data/published_models` in the existing `prediction-data` volume, shared by Backend and Worker. `/app/ml_models` in the image is only the bundled seed source (`EDGEML_BUNDLED_MODELS_ROOT`). Startup copies missing packages atomically under a file lock, never overwrites existing packages, and leaves the existing Registry lifecycle state intact. Local development keeps `backend/ml_models`.

For the first upgrade from the old writable-layer layout:

1. Pause browser/API writes and allow active training to finish. Stop any manually launched legacy workers; do not run old and new workers together.
2. Keep the existing Backend container and `prediction-data` volume. Do **not** run `docker compose down`, remove the old Backend, or use `down -v` before migration.
3. Run `deploy-docker.bat` (optionally `deploy-docker.bat 3`). Its preparation helper starts the existing Backend if stopped, stops old Compose Workers, and executes the stdlib migration script inside the old container. It copies old model packages into `/app/data/published_models` before Compose recreates containers. Original packages remain untouched; differing destination files abort deployment instead of overwriting.
4. Verify the model list and a prediction for an existing published model. On subsequent recreate operations, packages remain on the shared data volume.

`start-dev-docker.bat` refuses this legacy upgrade and directs you to the rebuild launcher; starting outdated images is not sufficient to activate the reliability fixes. If running Compose manually, run `prepare-docker-upgrade.bat rebuild` before the first `up --build`. Migration failure leaves original packages/container intact and legacy Workers stopped; resolve the conflict and rerun deployment. If the old container was already deleted, restore its model backup or republish the preserved trained models; migration cannot recover an erased writable layer. Keep the same Compose project name/volume when moving folders, or explicitly migrate the old volume.

New publications use model IDs as package folder names; renaming changes metadata only. Existing name-based packages remain compatible. Republishing a legacy model registers its ID-based package; older package copies are retained until an explicit operator cleanup, not automatically deleted during migration.

Workers use cross-process OS file locks in the shared training-jobs directory to hold job ownership. Claim and recovery share a short dispatch lock, and recovery skips live owners. Locks are released automatically on process termination; idle Workers periodically recover abandoned processing entries. Completed/cancelled records are acknowledged without retraining. Registry updates use a separate cross-process lock around the full read/modify/write transaction and unique atomic-replacement temporary files.

All Worker replicas must share the **same local filesystem/volume** for jobs and lock files. This implementation supports one Docker host or Windows local development; do not use isolated per-host directories or assume NFS/SMB lock semantics. At-least-once delivery remains: a crash between artifact creation and persisted job completion still requires future idempotent-output work (ROADMAP R19).
