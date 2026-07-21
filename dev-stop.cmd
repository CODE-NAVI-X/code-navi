@echo off
chcp 65001 >nul 2>&1

echo ============================================
echo   Code Navi - Stop Dev
echo ============================================
echo.

echo [1/2] Stopping backend (port 8000) ...
taskkill /FI "WINDOWTITLE eq Backend :8000*" /T /F >nul 2>&1
if %errorlevel%==0 (echo   Backend stopped.) else (echo   Backend window not found.)

echo [2/2] Stopping frontend (port 3000) ...
taskkill /FI "WINDOWTITLE eq Frontend :3000*" /T /F >nul 2>&1
if %errorlevel%==0 (echo   Frontend stopped.) else (echo   Frontend window not found.)

echo.
echo Cleaning ports ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING" 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1 && echo   Released port 8000 (PID %%a)
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000.*LISTENING" 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1 && echo   Released port 3000 (PID %%a)
)

echo.
echo ============================================
echo   All services stopped.
echo ============================================
pause