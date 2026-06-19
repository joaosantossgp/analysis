# Run the desktop app in dev mode with isolated repo-local data.
# This is the default dev workflow for safe downloads, resets, and experiments.
#
# Usage:
#   .\scripts\release\dev-desktop.ps1
#   .\scripts\release\dev-desktop.ps1 --debug    # opens DevTools
#
# Data directory: <repo>\data
# To test against release data, use .\scripts\release\dev-desktop-release-data.ps1.

param(
    [switch]$Debug
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)

Set-Location $repoRoot

$devDataDir = Join-Path $repoRoot "data"
Remove-Item Env:CVMANALYTICS_USE_RELEASE_DATA -ErrorAction SilentlyContinue
Remove-Item Env:CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES -ErrorAction SilentlyContinue
if (-not $env:CVM_DATA_DIR) {
    $env:CVM_DATA_DIR = $devDataDir
}

$args = @("--dev")
if ($Debug) { $args += "--debug" }

Write-Host "[dev-desktop] Starting dev desktop with isolated data..." -ForegroundColor Cyan
Write-Host "[dev-desktop] Data directory: $env:CVM_DATA_DIR" -ForegroundColor DarkCyan
Write-Host "[dev-desktop] Writes are enabled for this isolated dev data directory." -ForegroundColor DarkGreen
Write-Host ""

python -m desktop.app @args
