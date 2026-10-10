@echo off
chcp 65001 >nul
echo.
echo   [STOP] Dang dung tat ca service...

cd /d "%~dp0"
set PIDS_DIR=%CD%\.pids

REM Kill by PID files
if exist "%PIDS_DIR%\backend.pid" (
    for /f %%i in (%PIDS_DIR%\backend.pid) do taskkill /F /T /PID %%i 2>nul
    del "%PIDS_DIR%\backend.pid"
)
if exist "%PIDS_DIR%\frontend.pid" (
    for /f %%i in (%PIDS_DIR%\frontend.pid) do taskkill /F /T /PID %%i 2>nul
    del "%PIDS_DIR%\frontend.pid"
)

REM Kill by listening ports (3000 = next, 8000 = uvicorn, 5432 = postgres)
for %%p in (3000 8000 5432) do (
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":[%%p]" ^| findstr LISTENING') do (
        echo   Killing PID %%a on port %%p
        taskkill /F /PID %%a 2>nul
    )
)

set /p STOP_PG="Dung luon PostgreSQL container? (y/N): "
if /i "%STOP_PG%"=="y" docker stop ig-postgres >nul 2>&1

echo   Xong!
timeout /t 3 >nul
