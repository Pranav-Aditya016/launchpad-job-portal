<#
.SYNOPSIS
    Starts both LaunchPad dev servers: the FastAPI backend (uvicorn, port 8000)
    and the Next.js frontend (npm run dev, port 3000).

.DESCRIPTION
    Each server is launched in its own new PowerShell window so their logs stay
    separate and readable. Run this from the repository root:

        pwsh scripts/dev.ps1

    Stop a server with Ctrl+C in its own window, or just close that window.
    This script does not install dependencies — it checks for them first and
    tells you the exact command to run if something's missing.
#>

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot 'backend'
$frontendDir = Join-Path $repoRoot 'frontend'

# --- Preflight: fail fast with a clear message instead of a confusing crash
# in a spawned window if dependencies were never installed. ------------------

python -c "import uvicorn, fastapi" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Backend dependencies not found." -ForegroundColor Yellow
    Write-Host "Run this first, then re-run scripts/dev.ps1:" -ForegroundColor Yellow
    Write-Host "  cd backend; pip install -e `".[dev]`"" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path (Join-Path $frontendDir 'node_modules'))) {
    Write-Host "Frontend dependencies not found." -ForegroundColor Yellow
    Write-Host "Run this first, then re-run scripts/dev.ps1:" -ForegroundColor Yellow
    Write-Host "  cd frontend; npm install" -ForegroundColor Yellow
    exit 1
}

Write-Host "Starting backend  -> http://localhost:8000" -ForegroundColor Cyan
Start-Process pwsh -ArgumentList @(
    '-NoExit', '-Command',
    "Set-Location `"$backendDir`"; python -m uvicorn app.api:app --reload --host 0.0.0.0 --port 8000"
)

Write-Host "Starting frontend -> http://localhost:3000" -ForegroundColor Cyan
Start-Process pwsh -ArgumentList @(
    '-NoExit', '-Command',
    "Set-Location `"$frontendDir`"; npm run dev"
)

Write-Host ""
Write-Host "Backend:  http://localhost:8000"
Write-Host "Frontend: http://localhost:3000"
Write-Host ""
Write-Host "Each server is running in its own new window. Close a window (or Ctrl+C" -ForegroundColor DarkGray
Write-Host "inside it) to stop that server." -ForegroundColor DarkGray
