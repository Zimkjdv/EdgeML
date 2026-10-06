@echo off
setlocal EnableExtensions DisableDelayedExpansion

rem Run the MySQL prediction client against the existing local API.
rem Model, DB and batch settings are loaded from the shared client INI.
rem Credentials: environment variables, examples\.env.local, then masked prompts.
rem This launcher does not start the API, install packages, or drop any table.
set "EDGE_PREDICT_PYTHON=%~dp0backend\.venv\Scripts\python.exe"
set "EDGE_PREDICT_SCRIPT=%~dp0examples\piapifd_edge_prediction.py"

if not exist "%EDGE_PREDICT_PYTHON%" (
  echo [ERROR] backend\.venv\Scripts\python.exe was not found.
  echo Create the Python 3.12 environment and install dependencies first.
  exit /b 1
)
if not exist "%EDGE_PREDICT_SCRIPT%" (
  echo [ERROR] examples\piapifd_edge_prediction.py was not found.
  exit /b 1
)

pushd "%~dp0"
if errorlevel 1 exit /b 1

echo EdgeML DB prediction client: local API 8000 by default.
echo Model, source, target and batch settings: examples\piapifd_prediction.ini
echo Extra arguments override defaults. Source remains read-only; existing results are not overwritten.

"%EDGE_PREDICT_PYTHON%" -X utf8 -u "%EDGE_PREDICT_SCRIPT%" --api-url http://127.0.0.1:8000/api --mode write --init-target %*
set "EDGE_PREDICT_EXIT=%ERRORLEVEL%"
if not "%EDGE_PREDICT_EXIT%"=="0" echo [ERROR] Prediction stopped; review the message above. Completed batches remain saved.

popd
exit /b %EDGE_PREDICT_EXIT%
