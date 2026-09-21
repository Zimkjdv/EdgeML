@echo off
setlocal
cd /d "%~dp0"
rem Both launchers run this before Compose can recreate a legacy backend.
for /f "delims=" %%C in ('docker compose ps -a -q backend') do (
  call :prepare %%C "%~1"
  if errorlevel 1 exit /b 1
)
exit /b 0

:prepare
docker start %1 >nul
if errorlevel 1 exit /b 1
docker exec %1 python -c "import os,sys; sys.exit(10 if os.environ.get('EDGEML_MODELS_ROOT') == '/app/data/published_models' else 0)"
if errorlevel 11 exit /b 1
if errorlevel 10 exit /b 0
if errorlevel 1 exit /b 1
if /I not "%~2"=="rebuild" (
  echo [ERROR] Legacy Docker runtime detected. Run deploy-docker.bat to build and migrate this upgrade.
  exit /b 1
)
echo Preparing legacy storage upgrade. Pause browser and API writes until deployment finishes.
docker compose stop worker
if errorlevel 1 exit /b 1
docker exec -i %1 python - < backend\scripts\migrate_model_storage.py
if errorlevel 1 (
  echo [ERROR] Migration failed. Original backend packages are retained. Workers are stopped.
  echo Resolve the reported conflict before retrying deployment.
  exit /b 1
)
exit /b 0
