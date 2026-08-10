@echo off
setlocal EnableExtensions
chcp 65001 >nul

cd /d "%~dp0"
set "CODE_NAVI_DATABASE_URL=sqlite:///./.code-navi/local_demo.db"
set "CODE_NAVI_FRONTEND_PORT=3000"
set "CODE_NAVI_BACKEND_PORT=8000"

powershell -NoProfile -Command "if (Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq 3000 }) { exit 1 }"
if errorlevel 1 goto :port_in_use

powershell -NoProfile -Command "if (Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq 8000 }) { exit 1 }"
if errorlevel 1 (
  set "CODE_NAVI_BACKEND_PORT=8001"
  powershell -NoProfile -Command "if (Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq 8001 }) { exit 1 }"
  if errorlevel 1 goto :backend_port_in_use
  echo [INFO] Port 8000 is occupied by another local service; using 8001 for Code Navi backend.
)
set "NEXT_PUBLIC_CODE_NAVI_API_URL=http://127.0.0.1:%CODE_NAVI_BACKEND_PORT%"

if not exist ".venv\Scripts\python.exe" (
  echo [SETUP] Creating Python virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" -c "import alembic, code_navi, fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
  echo [SETUP] Installing Python dependencies. This may take a few minutes on first run...
  ".venv\Scripts\python.exe" -m pip install -e ".[dev,server,online]"
  if errorlevel 1 goto :error
)

if not exist "frontend\node_modules" (
  echo [SETUP] Installing frontend dependencies. This may take a few minutes on first run...
  pushd frontend
  call npm ci
  if errorlevel 1 (
    popd
    goto :error
  )
  popd
)

echo [SETUP] Applying local database migrations...
".venv\Scripts\python.exe" -m alembic upgrade head
if errorlevel 1 (
  echo [INFO] Checking whether this local demo database only needs its migration marker repaired...
  ".venv\Scripts\python.exe" scripts\repair_local_demo_migration.py
  if errorlevel 1 goto :error
)

echo.
echo Starting Code Navi...
echo Research page: http://127.0.0.1:%CODE_NAVI_FRONTEND_PORT%/research
echo Backend health: http://127.0.0.1:%CODE_NAVI_BACKEND_PORT%/health
echo Press Ctrl+C in this window to stop both services.
echo.
".venv\Scripts\python.exe" scripts\dev.py
goto :end

:error
echo.
echo [ERROR] Startup failed. Check the messages above, then run this file again.
pause
goto :end

:port_in_use
echo.
echo [ERROR] Port 3000 or 8000 is already in use. Close the existing Code Navi window first.
pause
goto :end

:backend_port_in_use
echo.
echo [ERROR] Ports 8000 and 8001 are both occupied. Close the conflicting service first.
pause
goto :end

:end
endlocal
