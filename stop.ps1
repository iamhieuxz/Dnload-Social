# Stop all services
$root    = $PSScriptRoot
$pidsDir = Join-Path $root ".pids"

Write-Host ""
Write-Host "  Stopping..." -ForegroundColor Yellow

$stopped = 0
foreach ($svc in @("backend", "frontend")) {
    $pidFile = Join-Path $pidsDir "$svc.pid"
    if (Test-Path $pidFile) {
        $pid = Get-Content $pidFile -ErrorAction SilentlyContinue
        if ($pid) {
            taskkill /F /T /PID $pid 2>$null
            Write-Host "    $svc (PID $pid) stopped" -ForegroundColor Green
            $stopped++
        }
        Remove-Item $pidFile -ErrorAction SilentlyContinue
    }
}

foreach ($port in @(8000, 3000)) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object {
            taskkill /F /T /PID $_.OwningProcess 2>$null
            Write-Host "    port $port freed" -ForegroundColor Green
            $stopped++
        }
}

if ($stopped -eq 0) {
    Write-Host "    (nothing running)" -ForegroundColor DarkGray
}

Write-Host ""
