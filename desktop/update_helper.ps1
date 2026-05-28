# update_helper.ps1 — Swaps a staged update over the running installation.
# Spawned as a detached process by updater.py so it outlives the app.
#
# Usage (internal — called by updater.py):
#   powershell.exe -NonInteractive -ExecutionPolicy Bypass -File update_helper.ps1 <NewPath> <CurrentPath>
#
# Safety contract (Phase 0):
#   - Strict allowlist: only CVMAnalytics.exe and _internal\ are touched.
#   - Never touches user-writable runtime data (data\, output\, logs\, cache\, tmp\, backup\, versions\).
#   - Pre-copy snapshot of overwritten files into %LOCALAPPDATA%\CVMAnalytics\update_rollback\<utc-ts>\.
param(
    [Parameter(Mandatory)][string]$New,
    [Parameter(Mandatory)][string]$Current
)

$ErrorActionPreference = "Stop"

# Allowlist: top-level entries of the bundle that the updater is permitted to swap.
$Allowlist = @("CVMAnalytics.exe", "_internal")

# Hard-deny list: paths under $Current that the helper must never read, copy over, or delete.
# Defense-in-depth — Phase 0 already moves these out of the install dir, but enforce here too.
$UserDataDirs = @("data", "output", "logs", "cache", "tmp", "backup", "versions", "update_rollback")

$AppDataRoot = Join-Path $env:LOCALAPPDATA "CVMAnalytics"
$LogPath = Join-Path $AppDataRoot "update_error.log"

function Write-UpdateLog {
    param([string]$Message)
    try {
        if (-not (Test-Path $AppDataRoot)) {
            New-Item -ItemType Directory -Force -Path $AppDataRoot | Out-Null
        }
        $line = "[{0}] {1}" -f (Get-Date -Format o), $Message
        Add-Content -Path $LogPath -Value $line -Encoding UTF8
    } catch {
        # Logging best-effort; do not raise.
    }
}

Write-UpdateLog "helper started: New=$New Current=$Current PID=$PID"

# Give the parent process time to fully exit before touching its files.
Start-Sleep -Seconds 3

try {
    if (-not (Test-Path $New))     { throw "staged path not found: $New" }
    if (-not (Test-Path $Current)) { throw "current path not found: $Current" }

    $timestamp = (Get-Date -Format "yyyyMMddTHHmmssZ").Replace(":", "")
    $RollbackDir = Join-Path (Join-Path $AppDataRoot "update_rollback") $timestamp
    New-Item -ItemType Directory -Force -Path $RollbackDir | Out-Null

    foreach ($entry in $Allowlist) {
        # Reject any allowlist entry that collides with a user-data directory name.
        if ($UserDataDirs -contains $entry) {
            throw "allowlist entry '$entry' collides with user-data dir name; aborting"
        }

        $srcPath = Join-Path $New     $entry
        $dstPath = Join-Path $Current $entry

        if (-not (Test-Path $srcPath)) {
            Write-UpdateLog "skip (missing in staged bundle): $entry"
            continue
        }

        # Snapshot existing target into rollback dir before overwrite.
        if (Test-Path $dstPath) {
            $rollbackTarget = Join-Path $RollbackDir $entry
            Copy-Item -Recurse -Force -Path $dstPath -Destination $rollbackTarget
            # Remove the existing target so recursive copy doesn't merge stale files.
            Remove-Item -Recurse -Force -Path $dstPath
        }

        Copy-Item -Recurse -Force -Path $srcPath -Destination $dstPath
        Write-UpdateLog "swapped: $entry"
    }

    # Sanity check: user-data dirs under $Current must still exist untouched (if they existed).
    foreach ($userDir in $UserDataDirs) {
        $candidate = Join-Path $Current $userDir
        if (Test-Path $candidate) {
            Write-UpdateLog "user-data dir preserved: $userDir"
        }
    }

    $relaunchExe = Join-Path $Current "CVMAnalytics.exe"
    if (-not (Test-Path $relaunchExe)) {
        throw "relaunch target not found after swap: $relaunchExe"
    }
    Write-UpdateLog "swap complete; relaunching: $relaunchExe"
    Start-Process -FilePath $relaunchExe -WorkingDirectory $Current
    Write-UpdateLog "relaunch issued OK"
} catch {
    Write-UpdateLog ("ERROR: " + $_.Exception.Message)
    # On failure: rollback dir is left in place for manual recovery; current install untouched
    # if the failure happened before any Copy-Item, or partially swapped otherwise.
}
