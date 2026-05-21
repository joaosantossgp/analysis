#!/usr/bin/env pwsh
# Test that the packaged ZIP can be launched after being downloaded from the internet
# (Mark-of-the-Web applied), extracted with Windows Explorer's default behavior,
# and run by a normal user.
#
# Usage:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_motw_launch.ps1 <zip-path>

param(
    [Parameter(Mandatory)][string]$ZipPath
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ZipPath)) { throw "zip not found: $ZipPath" }

$sandbox = Join-Path $env:TEMP ("cvm_motw_test_" + [Guid]::NewGuid().ToString("N").Substring(0,8))
New-Item -ItemType Directory -Force -Path $sandbox | Out-Null
$workZip = Join-Path $sandbox (Split-Path $ZipPath -Leaf)
Copy-Item -Path $ZipPath -Destination $workZip -Force

# Apply Zone.Identifier ADS — ZoneId=3 = Internet
$zoneContent = @"
[ZoneTransfer]
ZoneId=3
ReferrerUrl=https://github.com/joaosantossgp/analisys/releases/tag/v0.3.1
HostUrl=https://github.com/joaosantossgp/analisys/releases/download/v0.3.1/CVMAnalytics-windows-v0.3.1.zip
"@
Set-Content -Path "${workZip}:Zone.Identifier" -Value $zoneContent -Encoding utf8

Write-Host "[motw-test] sandbox: $sandbox"
Write-Host "[motw-test] MOTW applied to zip. Zone.Identifier content:"
Get-Content -Path "${workZip}" -Stream Zone.Identifier

$extracted = Join-Path $sandbox "CVMAnalytics-extracted"
Expand-Archive -Path $workZip -DestinationPath $extracted -Force
Write-Host "[motw-test] extracted to: $extracted"

$exe = Join-Path $extracted "CVMAnalytics.exe"
$dll = Join-Path $extracted "_internal\pythonnet\runtime\Python.Runtime.dll"
$deps = Join-Path $extracted "_internal\pythonnet\runtime\Python.Runtime.deps.json"

Write-Host "[motw-test] exe exists: $(Test-Path $exe)"
Write-Host "[motw-test] Python.Runtime.dll exists: $(Test-Path $dll)"
Write-Host "[motw-test] Python.Runtime.deps.json exists: $(Test-Path $deps)"

# Check MOTW propagation on inner files
foreach ($p in @($exe, $dll, $deps)) {
    try {
        $z = Get-Content -Path $p -Stream Zone.Identifier -ErrorAction Stop
        Write-Host "[motw-test] MOTW present on: $(Split-Path $p -Leaf)"
    } catch {
        Write-Host "[motw-test] no MOTW on:        $(Split-Path $p -Leaf)"
    }
}

Write-Host "[motw-test] launching exe..."
$proc = Start-Process -FilePath $exe -PassThru
Start-Sleep -Seconds 25

if ($proc.HasExited) {
    Write-Host "[motw-test] FAIL: process exited with code $($proc.ExitCode)"
    $report = @{
        Result = "FAIL"
        ExitCode = $proc.ExitCode
        Sandbox = $sandbox
    }
} else {
    Write-Host "[motw-test] PASS: process alive after 25s"
    # Check webview2 children
    $wv2 = @(Get-Process msedgewebview2 -ErrorAction SilentlyContinue)
    Write-Host "[motw-test] msedgewebview2 child count: $($wv2.Count)"
    $report = @{
        Result = "PASS"
        ExitCode = $null
        WebView2Children = $wv2.Count
        Sandbox = $sandbox
    }
    Stop-Process -Id $proc.Id -Force
}

# Cleanup spawned children
Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process msedgewebview2 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

$report | ConvertTo-Json
