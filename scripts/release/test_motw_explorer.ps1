# test_motw_explorer.ps1 — Reproduce the Windows Explorer "Extract All" failure mode.
#
# Unlike Expand-Archive (used in test_motw_launch.ps1), Windows Explorer's
# Extract All preserves Mark-of-the-Web on EXTRACTED files. This script
# simulates that by applying Zone.Identifier ADS to every .dll, .exe, .pyd,
# .node, and .ps1 inside an extracted bundle, then launches the exe and
# reports whether the app survives.
#
# Usage:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_motw_explorer.ps1 <zip-path>

param(
    [Parameter(Mandatory)][string]$ZipPath
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ZipPath)) { throw "zip not found: $ZipPath" }

$sandbox = Join-Path $env:TEMP ("cvm_motw_explorer_" + [Guid]::NewGuid().ToString("N").Substring(0,8))
New-Item -ItemType Directory -Force -Path $sandbox | Out-Null
$workZip = Join-Path $sandbox (Split-Path $ZipPath -Leaf)
Copy-Item -Path $ZipPath -Destination $workZip -Force

# Apply MOTW to the zip (like a browser download would)
$zoneContent = @"
[ZoneTransfer]
ZoneId=3
ReferrerUrl=https://github.com/joaosantossgp/analisys/releases/tag/v0.3.3
HostUrl=https://github.com/joaosantossgp/analisys/releases/download/v0.3.3/CVMAnalytics-windows-v0.3.3.zip
"@
Set-Content -Path "${workZip}:Zone.Identifier" -Value $zoneContent -Encoding utf8

$extracted = Join-Path $sandbox "extracted"
Expand-Archive -Path $workZip -DestinationPath $extracted -Force

# Simulate Explorer Extract All: propagate MOTW to every binary inside
Write-Host "[motw-explorer] applying MOTW to extracted DLLs/EXEs..."
$stamped = 0
Get-ChildItem -Path $extracted -Recurse -File -Include *.dll,*.exe,*.pyd,*.node,*.ps1 | ForEach-Object {
    Set-Content -Path "$($_.FullName):Zone.Identifier" -Value $zoneContent -Encoding utf8 -ErrorAction SilentlyContinue
    $stamped++
}
Write-Host "[motw-explorer] stamped $stamped files"

# Spot-check
$dll = Join-Path $extracted "_internal\pythonnet\runtime\Python.Runtime.dll"
$exe = Join-Path $extracted "CVMAnalytics.exe"
foreach ($p in @($exe, $dll)) {
    $name = Split-Path $p -Leaf
    try {
        Get-Content -Path $p -Stream Zone.Identifier -ErrorAction Stop | Out-Null
        Write-Host "[motw-explorer] MOTW present on $name"
    } catch {
        Write-Host "[motw-explorer] no MOTW on   $name"
    }
}

Write-Host "[motw-explorer] launching exe..."
$proc = Start-Process -FilePath $exe -PassThru
Start-Sleep -Seconds 30

if ($proc.HasExited) {
    Write-Host "[motw-explorer] FAIL: process exited with code $($proc.ExitCode)"
    $result = "FAIL"
    $code = $proc.ExitCode
} else {
    Write-Host "[motw-explorer] PASS: process alive after 30s"
    $wv2 = @(Get-Process msedgewebview2 -ErrorAction SilentlyContinue)
    Write-Host "[motw-explorer] msedgewebview2 children: $($wv2.Count)"
    $result = "PASS"
    $code = $null
    Stop-Process -Id $proc.Id -Force
}

Get-Process node, msedgewebview2 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# Re-check MOTW status on Python.Runtime.dll AFTER launch (should be stripped if v0.3.3 worked)
try {
    Get-Content -Path $dll -Stream Zone.Identifier -ErrorAction Stop | Out-Null
    Write-Host "[motw-explorer] AFTER LAUNCH: MOTW still on Python.Runtime.dll (strip failed)"
} catch {
    Write-Host "[motw-explorer] AFTER LAUNCH: MOTW removed from Python.Runtime.dll (strip succeeded)"
}

@{ Result = $result; ExitCode = $code; Sandbox = $sandbox; StampedFiles = $stamped } | ConvertTo-Json
