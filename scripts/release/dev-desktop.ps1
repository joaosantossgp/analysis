# Run the desktop app in dev mode with isolated dev data (repo-relative data/).
# This is the default dev workflow — data is separate from the release app.
#
# Usage:
#   .\scripts\dev-desktop.ps1
#   .\scripts\dev-desktop.ps1 --debug    # opens DevTools
#
# Data directory: {repo}/data/
# To use the release data directory instead, run dev-desktop-release-data.ps1

param(
    [switch]$Debug
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)

Set-Location $repoRoot

$args = @("--dev")
if ($Debug) { $args += "--debug" }

Write-Host "[dev-desktop] Starting dev desktop (isolated dev data)..." -ForegroundColor Cyan
Write-Host "[dev-desktop] Data directory: $repoRoot\data" -ForegroundColor DarkCyan
Write-Host ""

python -m desktop.app @args
