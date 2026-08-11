# Deployment

Run the complete stack with:

```bash
docker compose up --build
```

The backend listens on port 8000 and the frontend on port 5173. Set `EDGEML_MODELS_ROOT` to change the deployment model path and `EDGEML_MAX_UPLOAD_BYTES` to limit CSV upload size.

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

For local development with model training, run `start-dev-redis.bat`. It starts Docker Compose Redis, then launches the same Backend and Frontend plus a local Training Worker. Docker Desktop must be running. Both launchers prefer `backend/.venv` and fall back to `backend/.venv-local`.

For production, terminate TLS at the organization-approved reverse proxy and mount only trusted model artifacts read-only.
