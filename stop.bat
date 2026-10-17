@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo.
echo   [..] Stopping Docker Compose services...
docker compose stop
if errorlevel 1 (
    echo   [X] Could not stop the Compose stack. Check Docker Desktop and retry.
    pause
    exit /b 1
)

echo   [OK] Services stopped. Container data and downloaded files are preserved.
echo   Run start.bat to start the stack again.
echo.
pause
exit /b 0
