# EdgeML Development Memo

## 2026-09-21 reliability upgrade

The complete analysis and ordered follow-up work are in [ROADMAP.md](ROADMAP.md). This batch changes publication paths, Docker model persistence, Worker ownership/recovery and Registry transactions.

Existing Docker installations must first use `deploy-docker.bat`: pause API writes, finish training and stop manually launched legacy Workers. The launcher stops old Compose Workers and migrates packages from the original Backend container into the existing data Volume **before** recreation. Keep that old container until migration succeeds. Conflicts stop deployment without replacing old model files; `start-dev-docker.bat` directs legacy installations to rebuild first. See [migration and recovery instructions](docs/05_Deployment.md#model-storage-and-reliability-upgrade).

Do not delete `prediction-data` or mix old/new Worker versions. New Workers and Backend must share their jobs directory and published-model directory. File locking is supported on local Windows storage and a single Docker host's shared local Volume. Changes are not deployed merely by editing these files.

## Recommended workflow

EdgeML uses a local-first development workflow and Docker-based integration verification.

```text
Local: rapid development and tests
Docker: complete environment verification and deployment
GitHub: store the verified version
```

## Local development

### Windows launchers

Use the project-root launchers after installing backend and frontend dependencies:

```powershell
# Prediction only: Backend + Frontend
.\start-dev.bat

# Full local training workflow: Docker Redis + Backend + Frontend + Training Worker
.\start-dev-redis.bat
```

`start-dev-redis.bat` starts the Redis service with Docker Compose, calls `start-dev.bat`, and opens a local Training Worker terminal. Docker Desktop must be running. Do not run both launchers at the same time; the Redis launcher already includes the Prediction-only launcher.

The launchers prefer `backend/.venv` and fall back to `backend/.venv-local`.

Use the local Python environment for the FastAPI server and training worker. Run Redis through Docker:

```powershell
docker compose up -d redis
```

Start the backend in one terminal:

```powershell
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload
```

Start the training worker in a second terminal:

```powershell
cd backend
.venv\Scripts\activate
python -m app.workers.training_worker
```

Run the frontend locally in a third terminal:

```powershell
cd frontend
npm run dev
```

This setup makes backend, worker, and frontend changes available immediately without rebuilding images.

## Docker verification

The full Docker runtime uses a shared `edgeml-ml-base` build image for the Backend and Worker. The base image contains the common Python/ML dependencies; it is not a running container. On a new computer, or after changing `backend/requirements.txt`, use the project launcher so the base image is built first:

```powershell
.\deploy-docker.bat
```

`deploy-docker.bat` is both the first-build and rebuild command. It builds `edgeml-ml-base`, builds the application images, and runs `docker compose up -d --build --remove-orphans`. It does not pull an EdgeML application image from GitHub; it builds the current local workspace. Docker may pull missing public base images such as Python, Node, Nginx, or Redis.

### Docker command comparison

| Scenario | Recommended command |
| --- | --- |
| First deployment | `.\deploy-docker.bat` |
| Deploy after pulling new code | `.\deploy-docker.bat` |
| Modify normal application code | `docker compose up -d --build` |
| Modify `.env` | `docker compose up -d --build --force-recreate backend frontend` |
| Modify ML dependencies | `.\deploy-docker.bat` |
| Start existing services only | `.\start-dev-docker.bat` |


After a normal Backend, Worker, or Frontend source change, this is also sufficient:

```powershell
docker compose up -d --build
```

Compose recreates a service Container when its Image or configuration changes. If nothing relevant changed, it reuses the existing Container. The old Container is removed and replaced only after the new Image is built successfully; named Volumes are preserved.

Use `--force-recreate` when an environment or configuration change must definitely be injected into a new Container. For example, after changing the root `.env` file:

```powershell
docker compose up -d --build --force-recreate backend frontend
```

The Backend receives `EDGEML_API_TOKEN`, `EDGEML_WEB_USERNAME`, and `EDGEML_WEB_PASSWORD` at container creation time. The frontend no longer embeds credentials; it uses a browser login session. Recreate the backend after changing credentials; editing `.env` does not update an already-running process. Local development requires restarting the launcher. Rebuild the frontend once when migrating from the old token-embedded version. See `docs/10_Web_Authentication.md`.

For backend or worker changes only:

```powershell
docker compose up -d --build backend worker
```

For frontend changes only:

```powershell
docker compose up -d --build frontend
```

For a subsequent start without rebuilding existing Images:

```powershell
.\start-dev-docker.bat
```

This launcher requires that `edgeml-ml-base` and the application Images already exist. Use `deploy-docker.bat` after `git pull` or whenever a rebuild is needed.

Running containers do not automatically receive local source changes. Rebuild the affected service after modifying code that runs inside Docker.

To stop the Docker runtime while preserving application and Redis data:

```powershell
docker compose down
```

Do not use `docker compose down -v` during normal development. The `-v` option also deletes named Volumes, which can remove trained models, prediction history, and Redis queue/dead-letter state.

## Verification checklist

1. Run the backend tests:

   ```powershell
   cd backend
   .venv\Scripts\activate
   python -m pytest
   ```

2. Run the frontend production build when frontend code changes:

   ```powershell
   cd frontend
   npm run build
   ```

3. Check the Docker services:

   ```powershell
   docker compose ps
   ```

4. Check API readiness:

   ```text
   http://localhost:8000/health/ready
   ```

   The main local endpoints are:

   ```text
   API docs:       http://localhost:8000/docs
   API liveness:   http://localhost:8000/health
   API readiness:  http://localhost:8000/health/ready
   Model API:      http://localhost:8000/api/models
   Frontend:       http://localhost:5173
   ```

5. Verify Redis from the project root. Redis is a TCP service, so it is not opened in a browser:

   ```powershell
   cd C:\Users\2000640\Desktop\edge
   docker compose exec redis redis-cli ping
   ```

   A healthy Redis service returns:

   ```text
   PONG
   ```

6. Confirm that a training job can move from `queued` to `completed` when the Redis and worker services are running.

## Commit and push

### R05–R08 upgrade (2026-09-21)

- API authentication is now on by default. Keep `EDGEML_ANONYMOUS_API=false` and use the existing web/API credentials. For deliberate anonymous local development only, set `EDGEML_ANONYMOUS_API=true`, clear `EDGEML_API_TOKEN` and `EDGEML_WEB_PASSWORD` in the root `.env`, and restart `start-dev.bat` or `start-dev-redis.bat`. Token expiry/revocation no longer changes the policy. The local launcher and Docker Compose both pass the new setting; `.env` changes require a restart/recreate, not just hot reload.
- Restart local Backend and Worker together after this upgrade. For Docker, use `deploy-docker.bat` when ready to apply the new code; the code/test commit does not itself redeploy running services. Direct local uvicorn can load the root settings with `--env-file ..\.env` from `backend`.
- CSV/JSON integer features reject fractions, nonfinite input and overflow with `422`. Actual missing values still use the documented drop policy. Fix invalid source values or correct the manifest dtype rather than relying on truncation.
- Training, initial external testing and later evaluation now apply the same saved missing-row policy. Fold/class counts are validated after cleaning. Saved historical scores remain unchanged until retraining/re-evaluation.
- On a failed manual replay, check Queue Operations and the job status. If the ID remains in dead-letter with `status=queued` / `replay_pending=true`, retry replay after storage/Redis recovers. If it is already queued/running/completed and no longer in dead-letter, dispatch succeeded; another replay returns `404`. The prepared marker clears on Worker claim. Do not manually edit/delete Redis IDs or job/lock files to compensate for a lost HTTP response.
- Regression tests: run `python -m pytest -q` in `backend`; real-Redis tests additionally require `EDGEML_TEST_REDIS_URL` pointing at a separate test Redis. These tests create UUID-prefixed keys and clean their own keys only. Current verification uses Python 3.12 in disposable containers, copied example packages and temporary data, not business models or production queues.

### Publish verified changes

Commit only after local tests and the relevant Docker verification pass:

```powershell
git add <changed-files>
git commit -m "<commit message>"
git push origin main
```

Do not add generated model artifacts or local virtual-environment files unless they are explicitly part of the change.
