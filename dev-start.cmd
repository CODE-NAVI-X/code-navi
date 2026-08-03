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

echo [1/2] Starting backend (port 8000) ...
start "Backend :8000" /D "%PROJECT_DIR%" cmd /k ".venv\Scripts\python.exe -m uvicorn code_navi.server:app --app-dir src --reload --host 127.0.0.1 --port 8000"
timeout /t 2 /nobreak >nul

echo [2/2] Starting frontend (port 3000) ...
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
