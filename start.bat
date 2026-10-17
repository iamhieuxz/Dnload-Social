@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo   ===============================================
echo     Dnload Social - Docker One-Click Launcher
echo   ===============================================
echo.

where docker >nul 2>&1
if errorlevel 1 (
    echo   [X] Docker CLI was not found. Install Docker Desktop first.
    pause
    exit /b 1
)

docker info >nul 2>&1
if not errorlevel 1 goto DOCKER_READY
echo   [..] Starting Docker Desktop...
if not exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" goto DOCKER_MISSING
start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
set /a WAIT=0

:WAIT_DOCKER
docker info >nul 2>&1
if not errorlevel 1 goto DOCKER_READY
set /a WAIT+=1
if !WAIT! geq 60 goto DOCKER_TIMEOUT
timeout /t 2 /nobreak >nul
goto WAIT_DOCKER

:DOCKER_MISSING
echo   [X] Docker Desktop was not found. Start it manually, then retry.
pause
exit /b 1

:DOCKER_TIMEOUT
echo   [X] Docker engine did not become ready within 60 seconds.
pause
exit /b 1

:DOCKER_READY
echo   [OK] Docker engine is ready

if defined COOKIE_ENCRYPTION_KEY goto KEY_READY
set "ENV_COOKIE_KEY="
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b /i "COOKIE_ENCRYPTION_KEY=" ".env"`) do set "ENV_COOKIE_KEY=%%B"
)
if defined ENV_COOKIE_KEY (
    set "COOKIE_ENCRYPTION_KEY=!ENV_COOKIE_KEY!"
    goto KEY_READY
)

    echo   [..] Generating a persistent Fernet key in .env...
    for /f "delims=" %%K in ('powershell -NoProfile -Command "$b=New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); [Convert]::ToBase64String($b).Replace('+','-').Replace('/','_')"') do set "COOKIE_ENCRYPTION_KEY=%%K"
    if not defined COOKIE_ENCRYPTION_KEY (
        echo   [X] Could not generate COOKIE_ENCRYPTION_KEY.
        pause
        exit /b 1
    )
    >>".env" echo COOKIE_ENCRYPTION_KEY=%COOKIE_ENCRYPTION_KEY%

:KEY_READY

echo   [..] Building and starting Docker Compose services...
docker compose up --build -d
if errorlevel 1 (
    echo   [X] Docker Compose failed. Inspect output above and run:
    echo       docker compose logs
    pause
    exit /b 1
)

echo   [..] Waiting for backend and frontend...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; foreach ($url in @('http://localhost:8000/api/health','http://localhost:3000')) { $ready=$false; for ($i=0; $i -lt 90; $i++) { try { $r=Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400) { $ready=$true; break } } catch {}; Start-Sleep -Seconds 2 }; if (-not $ready) { Write-Error ('Timed out waiting for ' + $url); exit 1 } }; exit 0"
if errorlevel 1 (
    echo   [X] A service did not become ready. Inspect with: docker compose logs
    pause
    exit /b 1
)

echo.
echo   ===============================================
echo     Services are ready
echo   ===============================================
echo     Web UI:      http://localhost:3000
echo     Backend API: http://127.0.0.1:8000/docs
echo.
echo     Stop stack:  stop.bat
echo     Logs:        docker compose logs -f
echo.
start "" "http://localhost:3000"
pause
exit /b 0
