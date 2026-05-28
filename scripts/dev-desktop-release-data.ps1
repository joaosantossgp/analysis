# Run the desktop app in dev mode pointing at the RELEASE data directory.
# Use this to test against real data without building a release package.
#
# WARNING: This uses the same database as the installed release app.
# Destructive actions (database reset, onboarding reset) affect real user data.
# The Status page will show a warning when this mode is active.
#
# Usage:
#   .\scripts\dev-desktop-release-data.ps1
#   .\scripts\dev-desktop-release-data.ps1 --debug    # opens DevTools
#
# Data directory: %USERPROFILE%\Documents\CVMAnalytics
# To use isolated dev data instead, run dev-desktop.ps1

param(
    [switch]$Debug
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

Set-Location $repoRoot

$releaseDataDir = Join-Path $env:USERPROFILE "Documents\CVMAnalytics"
$env:CVMANALYTICS_USE_RELEASE_DATA = "1"

$extraArgs = @("--dev")
if ($Debug) { $extraArgs += "--debug" }

Write-Host "[dev-desktop-release-data] Starting dev desktop with RELEASE data..." -ForegroundColor Yellow
Write-Host "[dev-desktop-release-data] Data directory: $releaseDataDir" -ForegroundColor Yellow
Write-Host "[dev-desktop-release-data] WARNING: destructive actions affect real user data." -ForegroundColor Red
Write-Host ""

python -m desktop.app @extraArgs
