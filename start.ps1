# IG Downloader v7.0 — One-Click Launcher
# Run:   .\start.ps1
# Stop:  .\stop.ps1

#Requires -Version 5.1
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"

$root    = $PSScriptRoot
$logsDir = Join-Path $root "logs"
$pidsDir = Join-Path $root ".pids"
$dataDir = Join-Path $root "backend\data"
New-Item -ItemType Directory -Force -Path $logsDir, $pidsDir, $dataDir | Out-Null

$backendDir = Join-Path $root "backend"
$venvDir    = Join-Path $backendDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$dbPath     = Join-Path $dataDir "igdownloader.db"
$backendLog = Join-Path $logsDir "backend.log"
$frontendLog= Join-Path $logsDir "frontend.log"
$backendPid = Join-Path $pidsDir "backend.pid"
$frontendPid= Join-Path $pidsDir "frontend.pid"

# ── Helpers ────────────────────────────────────────────────────────────────

function Test-Command($cmd) { $null -ne (Get-Command $cmd -ErrorAction SilentlyContinue) }

function Wait-Http($url, $sec) {
    $client = New-Object System.Net.Http.HttpClient
    $client.Timeout = [TimeSpan]::FromSeconds(3)
    for ($i = 0; $i -lt $sec; $i++) {
        try {
            $r = $client.GetAsync($url).Result
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { $client.Dispose(); return $true }
            $r.Dispose()
        } catch {}
        Start-Sleep -Seconds 1
    }
    $client.Dispose()
    return $false
}

# ── Banner ─────────────────────────────────────────────────────────────────

function Show-Banner {
    param([string]$msg)
    Clear-Host
    $width = 56
    $pad   = [Math]::Max(0, ($width - $msg.Length) / 2)
    Write-Host ""
    Write-Host (" " * [Math]::Floor($pad)) -NoNewline
    Write-Host $msg -ForegroundColor Magenta
    Write-Host (" " * [Math]::Floor($pad)) -NoNewline
    Write-Host ("─" * [Math]::Ceiling(($width - $msg.Length) / 2 + ($width - $msg.Length) % 2)) -ForegroundColor Magenta
    Write-Host ""
}

# ── Prerequisites ──────────────────────────────────────────────────────────

Show-Banner "IG Downloader v7.0 — Starting"

$missing = @()
if (-not (Test-Command "python")) { $missing += "Python  (https://python.org)" }
if (-not (Test-Command "node"))   { $missing += "Node.js (https://nodejs.org)" }
if ($missing.Count -gt 0) {
    Write-Host "  Missing: $($missing -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "  Python $(python -Version 2>&1)" -ForegroundColor Green
Write-Host "  Node   $(node --version)"        -ForegroundColor Green
Write-Host ""

# ── Backend ────────────────────────────────────────────────────────────────

Write-Host "  Backend..." -NoNewline

# Copy .env if missing
if (-not (Test-Path (Join-Path $backendDir ".env"))) {
    Copy-Item (Join-Path $backendDir ".env.example") (Join-Path $backendDir ".env") -ErrorAction SilentlyContinue
}

# Create venv
if (-not (Test-Path $venvDir)) {
    python -m venv $venvDir 2>$null
}

# Install deps
& $venvPython -m pip install --quiet --disable-pip-version-check -r (Join-Path $backendDir "requirements.txt") 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host " FAIL" -ForegroundColor Red; exit 1 }

# Run migrations
& $venvPython -m alembic upgrade head 2>$null | Out-Null

# Kill old process
if (Test-Path $backendPid) {
    $old = Get-Content $backendPid -ErrorAction SilentlyContinue
    if ($old) { taskkill /F /T /PID $old 2>$null }
}
"" | Out-File $backendLog -Encoding UTF8

# Start uvicorn via cmd so it outlives the shell
$cmd = "/c cd /d `"$backendDir`" && set DATABASE_URL=sqlite+aiosqlite:///$dbPath && `"$venvPython`" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> `"$backendLog`" 2>&1"
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName    = "cmd.exe"
$psi.Arguments   = $cmd
$psi.UseShellExecute = $true
$psi.WindowStyle = "Hidden"
$psi.CreateNoWindow = $true
$proc = [System.Diagnostics.Process]::Start($psi)
Start-Sleep -Seconds 2
$proc.Id | Out-File $backendPid -Encoding ASCII

if (-not (Wait-Http "http://localhost:8000/api/health" 60)) {
    Write-Host " FAIL (backend not responding)" -ForegroundColor Red
    Get-Content $backendLog -Tail 10 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkRed }
    exit 1
}
Write-Host " OK" -ForegroundColor Green

# ── Frontend ───────────────────────────────────────────────────────────────

Write-Host "  Frontend..." -NoNewline

$nodeModules = Join-Path $root "frontend\node_modules"
if (-not (Test-Path $nodeModules)) {
    Push-Location (Join-Path $root "frontend")
    npm install --no-audit --no-fund --loglevel=error 2>$null
    Pop-Location
}

if (Test-Path $frontendPid) {
    $old = Get-Content $frontendPid -ErrorAction SilentlyContinue
    if ($old) { taskkill /F /T /PID $old 2>$null }
}
"" | Out-File $frontendLog -Encoding UTF8

$nodeDir = "C:\Program Files\nodejs"
$cmd = "/c cd /d `"$root\frontend`" && set PATH=$nodeDir;%PATH% && npx next dev -p 3000 >> `"$frontendLog`" 2>&1"
$psi2 = New-Object System.Diagnostics.ProcessStartInfo
$psi2.FileName    = "cmd.exe"
$psi2.Arguments   = $cmd
$psi2.UseShellExecute = $true
$psi2.WindowStyle = "Hidden"
$psi2.CreateNoWindow = $true
$proc2 = [System.Diagnostics.Process]::Start($psi2)
Start-Sleep -Seconds 2
$proc2.Id | Out-File $frontendPid -Encoding ASCII

if (-not (Wait-Http "http://localhost:3000" 60)) {
    Write-Host " WARN (may still be compiling)" -ForegroundColor Yellow
} else {
    Write-Host " OK" -ForegroundColor Green
}

# ── Done ────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "  Ready:" -ForegroundColor White
Write-Host "    Web UI    http://localhost:3000" -ForegroundColor Cyan
Write-Host "    API Docs  http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "    DB        $dbPath" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Stop: .\stop.ps1" -ForegroundColor DarkGray
Write-Host ""

Start-Sleep -Seconds 1
try { Start-Process "http://localhost:3000" } catch {}

# ── Monitor ────────────────────────────────────────────────────────────────

function Test-Port($port) {
    $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    return ($null -ne $c -and $c.Count -gt 0)
}

try {
    while ($true) {
        Start-Sleep -Seconds 3
        if (-not (Test-Port 8000)) {
            Write-Host ""
            Write-Host "  Backend stopped. Press Enter to exit." -ForegroundColor Yellow
            Read-Host
            break
        }
    }
} finally {
    Write-Host ""
    Write-Host "  Stopping services..." -ForegroundColor Yellow
    foreach ($port in @(8000, 3000)) {
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object { taskkill /F /T /PID $_.OwningProcess 2>$null }
    }
    Write-Host "  Done." -ForegroundColor Green
}
