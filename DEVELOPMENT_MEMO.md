# EdgeML Development Memo

## Recommended workflow

EdgeML uses a local-first development workflow and Docker-based integration verification.

```text
Local: rapid development and tests
Docker: complete environment verification and deployment
GitHub: store the verified version
```

## Local development

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

Before committing an infrastructure or application change, verify the complete Compose environment:

```powershell
docker compose up -d --build
```

For backend or worker changes only:

```powershell
docker compose up -d --build backend worker
```

For frontend changes only:

```powershell
docker compose up -d --build frontend
```

Running containers do not automatically receive local source changes. Rebuild the affected service after modifying code that runs inside Docker.

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
   cd C:\Users\Ryanisop\Desktop\EdgeML
   docker compose exec redis redis-cli ping
   ```

   A healthy Redis service returns:

   ```text
   PONG
   ```

6. Confirm that a training job can move from `queued` to `completed` when the Redis and worker services are running.

## Commit and push

Commit only after local tests and the relevant Docker verification pass:

```powershell
git add <changed-files>
git commit -m "<commit message>"
git push origin main
```

Do not add generated model artifacts or local virtual-environment files unless they are explicitly part of the change.
