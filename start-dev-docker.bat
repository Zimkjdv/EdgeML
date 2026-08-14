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
docker image inspect edgeml-ml-base:latest >nul 2>nul
if errorlevel 1 (
  echo [ERROR] edgeml-ml-base:latest was not found.
  echo Run .\deploy-docker.bat once to build the shared ML base and application images.
  pause
  exit /b 1
)

echo Starting EdgeML Docker services with %WORKER_REPLICAS% worker replica(s)...
docker compose up -d --scale worker=%WORKER_REPLICAS%
if errorlevel 1 (
  echo [ERROR] Docker services could not be started.
  echo Check that Docker host ports 8010, 5180, and 6380 are available.
  pause
  exit /b 1
)

docker compose ps
echo.
echo EdgeML Docker services are running.
echo Frontend: http://localhost:5180
echo API docs: http://localhost:8010/docs
endlocal
