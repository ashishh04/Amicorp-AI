<#
.SYNOPSIS
  Pack what the server needs into deploy\udap-deploy.tar.gz (deploy/README.md, step 2).

.DESCRIPTION
  The bundle holds the source the images are built from and the deployment files. It leaves out everything
  that is secret or belongs to this laptop: backend\.env, deploy\.env, the generated n8n copies (dev\n8n\out,
  deploy\n8n\out), the Python virtual environment, node_modules and build output.
#>
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$bundle = Join-Path $PSScriptRoot "udap-deploy.tar.gz"

$include = @(
    "backend/app", "backend/scripts", "backend/pyproject.toml", "backend/alembic.ini",
    "frontend",
    "n8n-workflows",
    "dev/n8n/make_local_workflows.py", "dev/n8n/workflow-ids.json",
    "deploy"
)
$exclude = @(
    "__pycache__", "*.pyc",
    "frontend/node_modules", "frontend/dist", "frontend/.angular", "frontend/.vscode",
    "deploy/.env", "deploy/n8n/out", "deploy/*.tar.gz"
)

if (Test-Path $bundle) { Remove-Item $bundle }
$tarArgs = @("-czf", $bundle, "-C", $root) + ($exclude | ForEach-Object { "--exclude=$_" }) + $include
& tar.exe @tarArgs
if ($LASTEXITCODE -ne 0) { throw "tar failed with exit code $LASTEXITCODE." }

# Refuse to hand over a bundle that carries a secret or a laptop-only folder.
$listing = & tar.exe -tzf $bundle
$leaks = $listing | Where-Object {
    $_ -match '(^|/)\.env$' -or $_ -match '(^|/)n8n/out(/|$)' -or $_ -match '(^|/)(node_modules|\.venv)(/|$)'
}
if ($leaks) {
    Remove-Item $bundle
    throw "The bundle would contain files that must stay on this laptop:`n$($leaks -join "`n")"
}

$size = [math]::Round((Get-Item $bundle).Length / 1MB, 1)
Write-Host "Wrote $bundle ($size MB, $($listing.Count) entries)." -ForegroundColor Green
Write-Host "Copy it to the server, for example:  scp `"$bundle`" <user>@<server>:~/"
