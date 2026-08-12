@echo off
setlocal

rem Start the complete EdgeML runtime from existing Docker images.
set "PROJECT_ROOT=%~dp0"
set "WORKER_REPLICAS=%~1"
if not defined WORKER_REPLICAS set "WORKER_REPLICAS=1"

where docker >nul 2>nul
if errorlevel 1 (
  echo [ERROR] docker was not found in PATH. Start Docker Desktop and try again.
  pause
  exit /b 1
)

cd /d "%PROJECT_ROOT%"
echo Starting EdgeML Docker services with %WORKER_REPLICAS% worker replica(s)...
docker compose up -d --scale worker=%WORKER_REPLICAS%
if errorlevel 1 (
  echo [ERROR] Docker services could not be started.
  echo If local Backend or Frontend is running, stop it before starting Docker.
  pause
  exit /b 1
)

docker compose ps
echo.
echo EdgeML Docker services are running.
echo Frontend: http://localhost:5173
echo API docs: http://localhost:8000/docs
endlocal
