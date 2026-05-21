# Real test of CI-published v0.3.3 with Windows Explorer MOTW simulation.
# Downloads asset via gh, applies MOTW to all binaries inside extracted bundle,
# launches the CI-built exe (which has a CVMAnalytics/ wrapper dir), reports
# liveness.
$ErrorActionPreference = "Stop"

$sandbox = Join-Path $env:TEMP ("cvm_ci_v033_" + [Guid]::NewGuid().ToString("N").Substring(0,8))
New-Item -ItemType Directory -Force -Path $sandbox | Out-Null

Push-Location $sandbox
try {
    gh release download v0.3.3 --pattern "CVMAnalytics-windows-v0.3.3.zip" -R joaosantossgp/analisys | Out-Null
    if (-not (Test-Path "CVMAnalytics-windows-v0.3.3.zip")) {
        throw "asset download failed"
    }
    Write-Host "[ci-test] downloaded: $(Get-Item 'CVMAnalytics-windows-v0.3.3.zip' | Select-Object -ExpandProperty Length) bytes"
} finally {
    Pop-Location
}

$zip = Join-Path $sandbox "CVMAnalytics-windows-v0.3.3.zip"

# Apply MOTW to the zip itself (download from Internet)
$zone = "[ZoneTransfer]`r`nZoneId=3"
$zipAds = $zip + ":Zone.Identifier"
Set-Content -Path $zipAds -Value $zone -Encoding utf8

# Extract via Expand-Archive (strips MOTW from extracted files), then RE-APPLY
# MOTW to every binary to simulate Windows Explorer "Extract All"
$extracted = Join-Path $sandbox "ext"
Expand-Archive -Path $zip -DestinationPath $extracted -Force

$inner = Get-ChildItem $extracted -Directory | Select-Object -First 1
Write-Host "[ci-test] zip wrapper dir: $($inner.Name)"

$stamped = 0
Get-ChildItem -Path $extracted -Recurse -File -Include *.dll,*.exe,*.pyd,*.node,*.ps1 | ForEach-Object {
    $adsPath = $_.FullName + ":Zone.Identifier"
    Set-Content -Path $adsPath -Value $zone -Encoding utf8 -ErrorAction SilentlyContinue
    $stamped++
}
Write-Host "[ci-test] stamped $stamped binaries with MOTW"

$exe = Join-Path $inner.FullName "CVMAnalytics.exe"
$dll = Join-Path $inner.FullName "_internal\pythonnet\runtime\Python.Runtime.dll"
Write-Host "[ci-test] exe: $exe"

# Confirm MOTW is on the DLL before launch
try {
    Get-Content -Path $dll -Stream Zone.Identifier -ErrorAction Stop | Out-Null
    Write-Host "[ci-test] MOTW present on Python.Runtime.dll (before launch)"
} catch {
    Write-Host "[ci-test] MOTW absent on Python.Runtime.dll (before launch) - strip already happened?"
}

Write-Host "[ci-test] launching..."
$proc = Start-Process -FilePath $exe -PassThru
Start-Sleep -Seconds 30

if ($proc.HasExited) {
    Write-Host "[ci-test] FAIL: process exited with code $($proc.ExitCode)"
    $result = "FAIL"
} else {
    Write-Host "[ci-test] PASS: process alive after 30s"
    $wv2 = @(Get-Process msedgewebview2 -ErrorAction SilentlyContinue)
    Write-Host "[ci-test] msedgewebview2 children: $($wv2.Count)"
    Stop-Process -Id $proc.Id -Force
    $result = "PASS"
}

# Post-launch MOTW check
try {
    Get-Content -Path $dll -Stream Zone.Identifier -ErrorAction Stop | Out-Null
    Write-Host "[ci-test] AFTER LAUNCH: MOTW STILL on Python.Runtime.dll (strip failed)"
} catch {
    Write-Host "[ci-test] AFTER LAUNCH: MOTW removed from Python.Runtime.dll (strip succeeded)"
}

Get-Process node,msedgewebview2 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

Write-Host "[ci-test] result: $result"
Write-Host "[ci-test] sandbox kept at: $sandbox"
