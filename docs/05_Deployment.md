# Deployment

Run the complete stack with:

```bash
docker compose up --build
```

The Docker containers listen internally on Backend port `8000`, Frontend Nginx port `80`, and Redis port `6379`. The default host mappings are Backend `8010`, Frontend `5180`, and Redis `6380`. Set `EDGEML_MODELS_ROOT` to change the deployment model path and `EDGEML_MAX_UPLOAD_BYTES` to limit CSV upload size.

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

For a complete Docker runtime without rebuilding, run `start-dev-docker.bat`. After local development has been tested, use `deploy-docker.bat` to rebuild and deploy the complete Compose project. Both scripts accept an optional worker replica count, such as `deploy-docker.bat 2`.

The hybrid local launcher and full Docker runtime can run together because they use separate host ports and Redis queues: local `8000`/`5173`/`6381`, Docker `8010`/`5180`/`6380`. Their data directories and worker processes remain independent.

For production, terminate TLS at the organization-approved reverse proxy and mount only trusted model artifacts read-only.
