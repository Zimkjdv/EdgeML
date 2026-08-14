@echo off
setlocal

rem Build and deploy the complete EdgeML project to Docker Compose.
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
echo Building and deploying EdgeML with %WORKER_REPLICAS% worker replica(s)...
docker compose up -d --build --remove-orphans --scale worker=%WORKER_REPLICAS%
if errorlevel 1 (
  echo [ERROR] EdgeML Docker deployment failed.
  echo Check that Docker host ports 8010, 5180, and 6380 are available.
  pause
  exit /b 1
)

docker compose ps
echo.
echo EdgeML has been deployed to Docker.
echo Frontend: http://localhost:5180
echo API docs: http://localhost:8010/docs
endlocal
