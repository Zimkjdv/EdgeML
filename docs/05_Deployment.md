# Deployment

Run the complete stack with:

```bash
docker compose up --build
```

The backend listens on port 8000 and the frontend on port 5173. Set `EDGEML_MODELS_ROOT` to change the deployment model path and `EDGEML_MAX_UPLOAD_BYTES` to limit CSV upload size.

## Windows local development

For a non-containerized development environment, run `start-dev.bat` in the repository root after the Python virtual environment and frontend dependencies have been installed. It launches Uvicorn with `--reload` and Vite in separate command windows.

For production, terminate TLS at the organization-approved reverse proxy and mount only trusted model artifacts read-only.
