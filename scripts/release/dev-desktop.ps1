# Run the desktop app in dev mode with an isolated writable data root.
#
# Usage:
#   .\scripts\release\dev-desktop.ps1
#   .\scripts\release\dev-desktop.ps1 --debug    # opens DevTools
#
# Data directory: <repo>\data\dev-runtime
# To use shared release data, run dev-desktop-release-data.ps1 explicitly.

param(
    [switch]$Debug
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)

Set-Location $repoRoot

$devDataDir = Join-Path $repoRoot "data\dev-runtime"
$env:CVM_DATA_DIR = $devDataDir
Remove-Item Env:CVMANALYTICS_USE_RELEASE_DATA -ErrorAction SilentlyContinue
Remove-Item Env:VITE_MOCK_BRIDGE -ErrorAction SilentlyContinue

$args = @("--dev")
if ($Debug) { $args += "--debug" }

Write-Host "[dev-desktop] Starting dev desktop with isolated writable data..." -ForegroundColor Cyan
Write-Host "[dev-desktop] Data directory: $devDataDir" -ForegroundColor DarkCyan
Write-Host ""

python -m desktop.app @args
