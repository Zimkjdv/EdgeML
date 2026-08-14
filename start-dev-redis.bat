@echo off
setlocal

rem EdgeML hybrid development launcher: Docker Redis plus local Backend, Frontend, and Worker
set "PROJECT_ROOT=%~dp0"
set "BACKEND_DIR=%PROJECT_ROOT%backend"
set "HYBRID_COMPOSE_FILE=%PROJECT_ROOT%docker-compose.hybrid-redis.yml"
set "HYBRID_COMPOSE_PROJECT=edgeml-hybrid-redis"
set "EDGEML_REDIS_URL=redis://localhost:6381/0"

where docker >nul 2>nul
if errorlevel 1 (
  echo [ERROR] docker was not found in PATH. Install Docker Desktop and open a new terminal.
  pause
  exit /b 1
)

if exist "%BACKEND_DIR%\.venv\Scripts\python.exe" (
  set "PYTHON_EXE=%BACKEND_DIR%\.venv\Scripts\python.exe"
) else if exist "%BACKEND_DIR%\.venv-local\Scripts\python.exe" (
  set "PYTHON_EXE=%BACKEND_DIR%\.venv-local\Scripts\python.exe"
) else (
  echo [ERROR] No backend virtual environment found.
  echo Create one in backend and install requirements.txt first.
  pause
  exit /b 1
)

echo Starting Docker Redis...
docker compose -p "%HYBRID_COMPOSE_PROJECT%" -f "%HYBRID_COMPOSE_FILE%" ps --services --filter status=running | findstr /x /c:"redis" >nul
if errorlevel 1 (
  docker compose -p "%HYBRID_COMPOSE_PROJECT%" -f "%HYBRID_COMPOSE_FILE%" up -d redis
  if errorlevel 1 (
    echo [ERROR] Redis could not be started. Check that Docker Desktop is running.
    pause
    exit /b 1
  )
) else (
  echo Docker Redis is already running. Skipping Redis startup.
)

call "%PROJECT_ROOT%start-dev.bat"
if errorlevel 1 exit /b 1

echo Starting EdgeML Training Worker...
start "EdgeML Training Worker" /D "%BACKEND_DIR%" cmd /k ""%PYTHON_EXE%" -m app.workers.training_worker"

echo Docker Redis plus local Backend, Frontend, and Training Worker have been started.
echo Hybrid Redis: localhost:6381
echo API docs: http://localhost:8000/docs
echo Frontend: http://localhost:5173
endlocal
