@echo off
chcp 65001 >nul 2>&1
set "PROJECT_DIR=%~dp0"
pushd "%PROJECT_DIR%" || exit /b 1

echo ============================================
echo   Code Navi - Start Dev
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment is missing.
    echo         Run: python -m venv .venv
    echo         Then install: .venv\Scripts\python.exe -m pip install -e ".[dev,server]"
    popd
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo [ERROR] Frontend dependencies are missing.
    echo         Run: cd frontend ^&^& npm ci
    popd
    pause
    exit /b 1
)

if not exist ".code-navi\provider.env" (
    echo [INFO] No local model configuration found.
    echo        Research chat will use basic rules until a provider is configured.
    echo        Run: .venv\Scripts\code-navi.exe configure-provider --provider deepseek
    echo.
)

echo [1/4] Applying database migrations ...
".venv\Scripts\python.exe" -m alembic upgrade head
if errorlevel 1 (
    echo.
    echo [ERROR] Database migration failed.
    echo For a database created before Alembic, run:
    echo   .venv\Scripts\python.exe -m alembic stamp 0001
    echo   .venv\Scripts\python.exe -m alembic upgrade head
    echo.
    popd
    pause
    exit /b 1
)

echo [2/4] Starting Piston execution service ...
docker compose up -d piston
if errorlevel 1 (
    echo [ERROR] Failed to start Docker/Piston. Please ensure Docker Desktop is running.
    popd
    pause
    exit /b 1
)

echo [3/4] Preparing Python runtime ...
set "PISTON_BASE_URL=http://127.0.0.1:2000"
set "PISTON_PYTHON_VERSION=3.12.0"
.venv\Scripts\python.exe -m code_navi.online_compiler.runtime_setup
if errorlevel 1 (
    echo [ERROR] Failed to prepare the Python runtime in Piston.
    popd
    pause
    exit /b 1
)

echo [4/4] Starting backend and frontend ...
start "Backend :8000" /D "%PROJECT_DIR%" cmd /k ".venv\Scripts\python.exe -m uvicorn code_navi.server:app --app-dir src --reload --host 127.0.0.1 --port 8000"
timeout /t 2 /nobreak >nul
start "Frontend :3000" /D "%PROJECT_DIR%frontend" cmd /k "npm.cmd run dev -- --port 3000"

echo.
echo ============================================
echo   Backend API : http://127.0.0.1:8000
echo   Frontend    : http://127.0.0.1:3000
echo   API Docs    : http://127.0.0.1:8000/docs
echo ============================================
echo.
echo Close: dev-stop.cmd
echo.
popd
pause