@echo off
chcp 65001 >nul 2>&1

echo ============================================
echo   Code Navi - Start Dev
echo ============================================
echo.

if not exist ".env" (
    echo [WARN] .env not found - create it with DEEPSEEK_API_KEY
    echo.
)

echo [1/2] Starting backend (port 8000) ...
start "Backend :8000" cmd /k ".venv\Scripts\python.exe -m uvicorn code_navi.server:app --reload --host 0.0.0.0 --port 8000"
timeout /t 2 /nobreak >nul

echo [2/2] Starting frontend (port 3000) ...
start "Frontend :3000" cmd /k "cd /d "%CD%\frontend" && npx next dev --port 3000"

echo.
echo ============================================
echo   Backend API : http://localhost:8000
echo   Frontend    : http://localhost:3000
echo   API Docs    : http://localhost:8000/docs
echo ============================================
echo.
echo Close: dev-stop.cmd
echo.
pause