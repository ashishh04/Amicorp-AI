<#
.SYNOPSIS
  Generate the local workflow copies and import them, with their credentials, into your local n8n.

.DESCRIPTION
  Run it once now, and again whenever the workflows in n8n-workflows/ change.
  n8n must be STOPPED while it runs. Workflows that already exist are updated in place
  (same IDs, see workflow-ids.json), and n8n's workflow history keeps their previous versions.
#>
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$root = (Resolve-Path (Join-Path $here "..\..")).Path

if (Get-NetTCPConnection -LocalPort 5678 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "n8n is running on port 5678. Stop it first (Ctrl+C in its window), then run this again." -ForegroundColor Yellow
    exit 1
}

$python = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

Write-Host "Generating local workflow copies..."
& $python (Join-Path $here "make_local_workflows.py")
if ($LASTEXITCODE -ne 0) { throw "Generating the local workflows failed." }

Write-Host "Importing credentials..."
n8n import:credentials --input="$here\out\credentials.json"
if ($LASTEXITCODE -ne 0) { throw "Importing credentials failed." }

Write-Host "Importing workflows..."
n8n import:workflow --separate --input="$here\out\workflows"
if ($LASTEXITCODE -ne 0) { throw "Importing workflows failed." }

Write-Host ""
Write-Host "Done. Start n8n with:  .\dev\n8n\start-n8n-local.ps1" -ForegroundColor Green
