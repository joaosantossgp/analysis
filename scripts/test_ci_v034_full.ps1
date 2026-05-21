# Full Phase 0 contract validation against the v0.3.4 CI-published asset.
# - Fresh install with MOTW (Explorer extract simulation)
# - Updater contract: discovery + download + stage + helper sandbox swap
$ErrorActionPreference = "Stop"

$sandbox = Join-Path $env:TEMP ("cvm_v034_full_" + [Guid]::NewGuid().ToString("N").Substring(0,8))
New-Item -ItemType Directory -Force -Path $sandbox | Out-Null

Push-Location $sandbox
try {
    gh release download v0.3.4 --pattern "CVMAnalytics-windows-v0.3.4.zip" -R joaosantossgp/analisys | Out-Null
    if (-not (Test-Path "CVMAnalytics-windows-v0.3.4.zip")) {
        throw "asset download failed"
    }
    $zipSize = (Get-Item "CVMAnalytics-windows-v0.3.4.zip").Length
    Write-Host "[v034-test] downloaded zip size: $zipSize bytes"
} finally {
    Pop-Location
}

$zip = Join-Path $sandbox "CVMAnalytics-windows-v0.3.4.zip"

# --- 1) FRESH INSTALL + MOTW ---------------------------------------------------
Write-Host "`n=== 1) FRESH INSTALL + MOTW ==="

$zone = "[ZoneTransfer]`r`nZoneId=3"
$zipAds = $zip + ":Zone.Identifier"
Set-Content -Path $zipAds -Value $zone -Encoding utf8

$installDir = Join-Path $sandbox "install"
Expand-Archive -Path $zip -DestinationPath $installDir -Force

$stamped = 0
Get-ChildItem -Path $installDir -Recurse -File -Include *.dll,*.exe,*.pyd,*.node,*.ps1 | ForEach-Object {
    $adsPath = $_.FullName + ":Zone.Identifier"
    Set-Content -Path $adsPath -Value $zone -Encoding utf8 -ErrorAction SilentlyContinue
    $stamped++
}
Write-Host "[v034-test] stamped $stamped binaries with MOTW"

$exe = Join-Path $installDir "CVMAnalytics.exe"
Write-Host "[v034-test] exe: $exe"

# Wipe LOCALAPPDATA so we can prove fresh init
$userRoot = Join-Path $env:LOCALAPPDATA "CVMAnalytics"
if (Test-Path $userRoot) { Remove-Item -Recurse -Force $userRoot }

$proc = Start-Process -FilePath $exe -PassThru
Start-Sleep -Seconds 30

if ($proc.HasExited) {
    Write-Host "[v034-test] FAIL fresh install: exited code $($proc.ExitCode)"
    $fresh = "FAIL"
} else {
    $wv2 = @(Get-Process msedgewebview2 -ErrorAction SilentlyContinue)
    Write-Host "[v034-test] PASS fresh install: alive, msedgewebview2 children = $($wv2.Count)"
    $fresh = "PASS"
    Stop-Process -Id $proc.Id -Force
}
Get-Process node,msedgewebview2 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# Verify LOCALAPPDATA DB
$db = Join-Path $userRoot "db\cvm_financials.db"
if (Test-Path $db) {
    Write-Host "[v034-test] LOCALAPPDATA DB present: $db"
} else {
    Write-Host "[v034-test] WARN: LOCALAPPDATA DB missing"
}

# --- 2) UPDATER STAGING + HELPER SANDBOX SWAP ---------------------------------
Write-Host "`n=== 2) UPDATER STAGING + HELPER SANDBOX SWAP ==="

# Build a fake "current install" with user data + an older exe, then swap to v0.3.4 via the helper.
$currentDir = Join-Path $sandbox "current-install"
New-Item -ItemType Directory -Force -Path $currentDir | Out-Null
# Older exe with marker
Set-Content -Path (Join-Path $currentDir "CVMAnalytics.exe") -Value "OLD-EXE-V032" -Encoding utf8
New-Item -ItemType Directory -Force -Path (Join-Path $currentDir "_internal") | Out-Null
Set-Content -Path (Join-Path $currentDir "_internal\OLD_MARKER.txt") -Value "OLD-INTERNAL" -Encoding utf8
# User data
New-Item -ItemType Directory -Force -Path (Join-Path $currentDir "data\db") | Out-Null
Set-Content -Path (Join-Path $currentDir "data\db\cvm_financials.db") -Value "USER-DB-MUST-SURVIVE" -Encoding utf8
Set-Content -Path (Join-Path $currentDir "data\db\cvm_financials.db-wal") -Value "wal-bytes" -Encoding utf8
New-Item -ItemType Directory -Force -Path (Join-Path $currentDir "output") | Out-Null
Set-Content -Path (Join-Path $currentDir "output\report.xlsx") -Value "USER-REPORT" -Encoding utf8

# Stage the new version (extract zip into staging dir, same as updater.py download_and_stage)
$staged = Join-Path $sandbox "staged"
Expand-Archive -Path $zip -DestinationPath $staged -Force
Write-Host "[v034-test] staged root entries: $((Get-ChildItem $staged -Name) -join ', ')"

# Use the bundled helper from staged (matches production path resolution)
$helperSrc = Join-Path $staged "_internal\update_helper.ps1"
if (-not (Test-Path $helperSrc)) {
    Write-Host "[v034-test] FAIL: update_helper.ps1 not bundled at $helperSrc"
    exit 1
}
# Patch helper to skip 3s sleep + skip relaunch
$helperPatched = Join-Path $sandbox "helper_test.ps1"
$src = Get-Content $helperSrc -Raw
$src = $src -replace 'Start-Sleep -Seconds 3','# sleep skipped'
$src = $src -replace 'Start-Process -FilePath.*','# relaunch skipped'
Set-Content -Path $helperPatched -Value $src -Encoding utf8

# Sandbox LOCALAPPDATA so rollback writes don't pollute the real user dir
$origAppData = $env:LOCALAPPDATA
$env:LOCALAPPDATA = Join-Path $sandbox "appdata"
New-Item -ItemType Directory -Force -Path $env:LOCALAPPDATA | Out-Null

Write-Host "[v034-test] invoking helper..."
& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $helperPatched $staged $currentDir
$helperExit = $LASTEXITCODE
Write-Host "[v034-test] helper exit code: $helperExit"

# Verify swap
$newExeContent = Get-Content (Join-Path $currentDir "CVMAnalytics.exe") -TotalCount 1 -ErrorAction SilentlyContinue
$exeReplaced = $newExeContent -ne "OLD-EXE-V032"
Write-Host "[v034-test] exe replaced: $exeReplaced"

$newInternalMarker = Test-Path (Join-Path $currentDir "_internal\OLD_MARKER.txt")
Write-Host "[v034-test] old _internal marker present (should be False): $newInternalMarker"

# User data preserved?
$dbContent = Get-Content (Join-Path $currentDir "data\db\cvm_financials.db") -Raw
$reportContent = Get-Content (Join-Path $currentDir "output\report.xlsx") -Raw
$dbOk = $dbContent.Trim() -eq "USER-DB-MUST-SURVIVE"
$reportOk = $reportContent.Trim() -eq "USER-REPORT"
Write-Host "[v034-test] user DB preserved: $dbOk"
Write-Host "[v034-test] user output preserved: $reportOk"

# Rollback dir created?
$rollbackRoot = Join-Path $env:LOCALAPPDATA "CVMAnalytics\update_rollback"
$rollbackOk = Test-Path $rollbackRoot
if ($rollbackOk) {
    $rb = @(Get-ChildItem $rollbackRoot -Directory)
    Write-Host "[v034-test] rollback created: $($rb.Count) directory(ies)"
    if ($rb.Count -gt 0) {
        $rbContents = @(Get-ChildItem $rb[0].FullName)
        Write-Host "[v034-test] rollback contents: $($rbContents.Name -join ', ')"
    }
} else {
    Write-Host "[v034-test] rollback dir missing"
}

# Restore LOCALAPPDATA
$env:LOCALAPPDATA = $origAppData

# --- summary ------------------------------------------------------------------
Write-Host "`n=== RESULT ==="
$updaterPass = ($helperExit -eq 0) -and $exeReplaced -and (-not $newInternalMarker) -and $dbOk -and $reportOk -and $rollbackOk
Write-Host "fresh_install: $fresh"
Write-Host "updater_contract: $(if ($updaterPass) {'PASS'} else {'FAIL'})"
Write-Host "sandbox: $sandbox"

# Cleanup user LOCALAPPDATA from fresh install test
if (Test-Path $userRoot) { Remove-Item -Recurse -Force $userRoot -ErrorAction SilentlyContinue }
