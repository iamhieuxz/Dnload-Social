@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

REM ============================================================================
REM  Instagram Downloader v7.0 — One-Click Launcher (Windows CMD)
REM  Chạy:  start.bat
REM  Dừng:  stop.bat    (hoặc nhấn Ctrl+C)
REM ============================================================================

cd /d "%~dp0"

set LOGS_DIR=%CD%\logs
set PIDS_DIR=%CD%\.pids
if not exist "%LOGS_DIR%" mkdir "%LOGS_DIR%"
if not exist "%PIDS_DIR%" mkdir "%PIDS_DIR%"

echo.
echo   =======================================================
echo     Instagram Downloader v7.0  -  One-Click Launcher
echo   =======================================================
echo.

REM ---- Check prerequisites ----
echo   [1/6] Kiem tra moi truong...
where python >nul 2>&1 || (echo   [X] Python chua cai & exit /b 1)
where node   >nul 2>&1 || (echo   [X] Node.js chua cai & exit /b 1)
where docker >nul 2>&1 || (echo   [X] Docker chua cai & exit /b 1)
docker info >nul 2>&1 || (echo   [X] Docker Desktop chua chay & exit /b 1)
echo   [OK] Python / Node / Docker OK
echo.

REM ---- PostgreSQL ----
echo   [2/6] Khoi dong PostgreSQL...
docker ps -a --format "{{.Names}}" | findstr /B "ig-postgres" >nul 2>&1
if %errorlevel%==0 (
    docker ps --format "{{.Names}}" | findstr /B "ig-postgres" >nul 2>&1
    if %errorlevel%==0 (
        echo   [OK] Container ig-postgres dang chay
    ) else (
        echo   [..] Starting existing container...
        docker start ig-postgres >nul
    )
) else (
    echo   [..] Tao container moi...
    docker run -d --name ig-postgres -e POSTGRES_USER=iguser -e POSTGRES_PASSWORD=igpass -e POSTGRES_DB=igdownloader -p 5432:5432 -v ig_pg_data:/var/lib/postgresql/data postgres:16-alpine >nul
)
echo   [OK] PostgreSQL OK
echo.

REM ---- Backend env + venv ----
echo   [3/6] Chuan bi Backend...
if not exist "backend\.env" copy "backend\.env.example" "backend\.env" >nul

if not exist "backend\.venv\Scripts\python.exe" (
    echo   [..] Tao Python venv...
    python -m venv backend\.venv
)

set PY=backend\.venv\Scripts\python.exe

echo   [..] Cai dat Python dependencies (lan dau co the mat 1-2 phut)...
"%PY%" -m pip install --quiet --disable-pip-version-check -r backend\requirements.txt
if %errorlevel% neq 0 (echo   [X] pip install that bai & exit /b 1)
echo   [OK] Backend deps OK
echo.

REM ---- Migrations ----
echo   [4/6] Chay Alembic migrations...
"%PY%" -m alembic upgrade head
echo   [OK] Schema san sang
echo.

REM ---- Start backend in background ----
echo   [5/6] Khoi dong Backend (port 8000)...
if exist "%PIDS_DIR%\backend.pid" (
    for /f %%i in (%PIDS_DIR%\backend.pid) do taskkill /F /T /PID %%i >nul 2>&1
    del %PIDS_DIR%\backend.pid
)

set BACKEND_LOG=%LOGS_DIR%\backend.log
start /min "IG-Backend" cmd /c "cd backend && "%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > "%BACKEND_LOG%" 2>&1"
echo %errorlevel% > %PIDS_DIR%\backend.pid

REM Wait for backend
echo   [..] Doi backend san sang...
set /a elapsed=0
:WAIT_BACKEND
if %elapsed% geq 30 goto :BACKEND_FAIL
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://localhost:8000/api/health' -UseBasicParsing -TimeoutSec 2).StatusCode } catch { exit 1 }" >nul 2>&1
if %errorlevel%==0 goto :BACKEND_OK
set /a elapsed+=1
ping -n 2 127.0.0.1 >nul
goto :WAIT_BACKEND
:BACKEND_OK
echo   [OK] Backend OK
goto :BACKEND_DONE
:BACKEND_FAIL
echo   [X] Backend khong khoi dong duoc. Xem logs\backend.log
exit /b 1
:BACKEND_DONE
echo.

REM ---- Frontend ----
echo   [6/6] Chuan bi va khoi dong Frontend (port 3000)...
if not exist "frontend\node_modules" (
    echo   [..] npm install (lan dau co the mat 2-5 phut)...
    cd frontend
    call npm install --no-audit --no-fund --loglevel=error
    if %errorlevel% neq 0 (echo   [X] npm install that bai & exit /b 1)
    cd ..
)
echo   [OK] Frontend deps OK

if exist "%PIDS_DIR%\frontend.pid" (
    for /f %%i in (%PIDS_DIR%\frontend.pid) do taskkill /F /T /PID %%i >nul 2>&1
    del %PIDS_DIR%\frontend.pid
)

set FRONTEND_LOG=%LOGS_DIR%\frontend.log
start /min "IG-Frontend" cmd /c "cd frontend && npx next dev -p 3000 > "%FRONTEND_LOG%" 2>&1"

echo   [..] Doi frontend san sang (lan dau co the mat 30-60s compile)...
set /a elapsed=0
:WAIT_FRONTEND
if %elapsed% geq 90 goto :FRONTEND_WARN
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://localhost:3000' -UseBasicParsing -TimeoutSec 2).StatusCode } catch { exit 1 }" >nul 2>&1
if %errorlevel%==0 goto :FRONTEND_OK
set /a elapsed+=1
ping -n 2 127.0.0.1 >nul
goto :WAIT_FRONTEND
:FRONTEND_OK
echo   [OK] Frontend OK
goto :FRONTEND_DONE
:FRONTEND_WARN
echo   [!] Frontend cham phan hoi (dang compile?). Kiem tra logs\frontend.log
:FRONTEND_DONE
echo.

REM ---- Done ----
echo   =======================================================
echo     *  HE THONG DA SAN SANG  *
echo   =======================================================
echo.
echo     Web UI:       http://localhost:3000
echo     Backend API:  http://localhost:8000/docs
echo     PostgreSQL:   localhost:5432  (iguser/igpass/igdownloader)
echo.
echo     Logs:         .\logs\backend.log
echo                   .\logs\frontend.log
echo     Dung tat ca:  .\stop.bat
echo.

REM Open browser
start "" "http://localhost:3000"

echo   Nhan phim bat ky de dung tat ca service...
pause >nul

REM Cleanup
if exist "%PIDS_DIR%\backend.pid" (
    for /f %%i in (%PIDS_DIR%\backend.pid) do taskkill /F /T /PID %%i >nul 2>&1
    del %PIDS_DIR%\backend.pid
)
if exist "%PIDS_DIR%\frontend.pid" (
    for /f %%i in (%PIDS_DIR%\frontend.pid) do taskkill /F /T /PID %%i >nul 2>&1
    del %PIDS_DIR%\frontend.pid
)
echo   Da dung tat ca service.
endlocal
