@echo off
setlocal

rem EdgeML local development launcher (Windows)
set "PROJECT_ROOT=%~dp0"
set "BACKEND_DIR=%PROJECT_ROOT%backend"
set "FRONTEND_DIR=%PROJECT_ROOT%frontend"

if exist "%BACKEND_DIR%\.venv\Scripts\python.exe" (
  set "PYTHON_EXE=%BACKEND_DIR%\.venv\Scripts\python.exe"
) else if exist "%BACKEND_DIR%\.venv-local\Scripts\python.exe" (
  set "PYTHON_EXE=%BACKEND_DIR%\.venv-local\Scripts\python.exe"
) else (
  echo [ERROR] No backend virtual environment found.
  echo Create one in backend with: python -m venv .venv
  echo Then install dependencies with: .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm.cmd was not found in PATH. Install Node.js LTS and open a new terminal.
  pause
  exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules" (
  echo [ERROR] Frontend dependencies are missing.
  echo Run: cd /d "%FRONTEND_DIR%" ^&^& npm.cmd install
  pause
  exit /b 1
)

echo Starting EdgeML development services...
start "EdgeML Backend" /D "%BACKEND_DIR%" cmd /k ""%PYTHON_EXE%" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
start "EdgeML Frontend" /D "%FRONTEND_DIR%" cmd /k "npm.cmd run dev"

echo Backend API docs: http://localhost:8000/docs
echo Frontend:         http://localhost:5173
echo Two service windows have been opened. Close them to stop EdgeML.
endlocal

