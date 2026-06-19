# Run the desktop app in dev mode with the shared Documents data root.
# This is the default dev workflow so local testing matches the release app.
#
# Usage:
#   .\scripts\release\dev-desktop.ps1
#   .\scripts\release\dev-desktop.ps1 --debug    # opens DevTools
#
# Data directory: %USERPROFILE%\Documents\CVMAnalytics
# To use isolated dev data, set CVM_DATA_DIR explicitly before launching.

param(
    [switch]$Debug
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)

Set-Location $repoRoot

$releaseDataDir = Join-Path $env:USERPROFILE "Documents\CVMAnalytics"
$env:CVMANALYTICS_USE_RELEASE_DATA = "1"

$args = @("--dev")
if ($Debug) { $args += "--debug" }

Write-Host "[dev-desktop] Starting dev desktop with shared Documents data..." -ForegroundColor Cyan
Write-Host "[dev-desktop] Data directory: $releaseDataDir" -ForegroundColor DarkCyan
Write-Host "[dev-desktop] Destructive actions are blocked by default in dev shared-data mode." -ForegroundColor DarkYellow
Write-Host ""

python -m desktop.app @args
