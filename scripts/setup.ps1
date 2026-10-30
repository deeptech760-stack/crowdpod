# One-time setup on Windows: Python packages, Chromium for the browser agents, and the UI.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "Install uv first: https://docs.astral.sh/uv/getting-started/installation/" }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw "Install Node.js 20.9 or newer: https://nodejs.org" }
$nodeVersion = [version](node -p "process.versions.node")
if ($nodeVersion -lt [version]"20.9.0") { throw "Node.js 20.9 or newer is needed (found $nodeVersion)" }

Write-Host "Backend: Python 3.11 and the exact package versions from uv.lock"
Push-Location backend
uv sync --frozen; if ($LASTEXITCODE) { throw "uv sync failed" }
uv run playwright install chromium; if ($LASTEXITCODE) { throw "Chromium install failed" }
Pop-Location

Write-Host "Frontend: the exact package versions from package-lock.json"
Push-Location frontend
npm.cmd ci; if ($LASTEXITCODE) { throw "npm ci failed" }
Pop-Location

Write-Host "Done. Start Crowdpod with: .\scripts\start.ps1"
