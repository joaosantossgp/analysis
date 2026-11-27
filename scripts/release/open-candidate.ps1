#!/usr/bin/env pwsh
# Download, verify and open a publication candidate built by the Release Desktop
# workflow, so the owner tests the exact file before approving it (issue #630).
# Contract: docs/release-process.md, "Testing a candidate".
#
# Usage:
#   .\scripts\release\open-candidate.ps1 latest
#   .\scripts\release\open-candidate.ps1 <Release Desktop run id>
#
# "latest" is the newest Release Desktop run that built a candidate, including
# one waiting for approval and dry runs. The candidate is extracted to
# %TEMP%\CVMAnalytics-candidates\<version>, and the previous one there is
# removed on every run. The candidate runs against the installed app's data
# (%USERPROFILE%\Documents\CVMAnalytics) and never touches the installed app's
# own files.

param(
    [Parameter(Mandatory)][string]$Candidate
)

$ErrorActionPreference = "Stop"
$repo = "joaosantossgp/analysis"
$root = Join-Path ([System.IO.Path]::GetTempPath()) "CVMAnalytics-candidates"

function Invoke-GhApi {
    param([string]$Path)
    $ErrorActionPreference = "Continue"  # gh reports failure by exit code; its own message goes to stderr
    $json = gh api $Path
    if ($LASTEXITCODE -ne 0) { return $null }
    return ($json | Out-String | ConvertFrom-Json)
}

# Resolve the run.
if ($Candidate -eq "latest") {
    $listing = Invoke-GhApi "repos/$repo/actions/artifacts?name=publication-candidate&per_page=100"
    if (-not $listing) { throw "Could not list candidates in $repo (see the gh error above)." }
    $newest = $listing.artifacts | Where-Object { -not $_.expired } | Sort-Object created_at -Descending | Select-Object -First 1
    if (-not $newest) { throw "No Release Desktop run in $repo has a candidate that has not expired. Re-run the workflow to build one." }
    $runId = [string]$newest.workflow_run.id
} elseif ($Candidate -match '^\d+$') {
    $runId = $Candidate
} else {
    throw "The candidate must be a Release Desktop run id or 'latest', not '$Candidate'."
}

$run = Invoke-GhApi "repos/$repo/actions/runs/$runId"
if (-not $run) { throw "Run $runId was not found in $repo, or GitHub could not be reached (see the gh error above)." }
if ($run.path -notlike ".github/workflows/release-desktop.yml*") {
    throw "Run $runId is a '$($run.name)' run, not a Release Desktop run: $($run.html_url)"
}

$artifacts = Invoke-GhApi "repos/$repo/actions/runs/$runId/artifacts"
if (-not $artifacts) { throw "Could not list the artifacts of run $runId (see the gh error above)." }
$package = $artifacts.artifacts | Where-Object { $_.name -eq "publication-candidate" } | Select-Object -First 1
if (-not $package) {
    if ($run.status -ne "completed") {
        throw "Run $runId has not built its candidate yet (status: $($run.status)). Wait for its Build candidate job: $($run.html_url)"
    }
    throw "Run $runId built no candidate (conclusion: $($run.conclusion)): its decision published nothing or its build failed. $($run.html_url)"
}
if ($package.expired) {
    throw "The candidate of run $runId expired on $($package.expires_at). Re-run the workflow to build a new one: $($run.html_url)"
}

# A running copy would hold the runtime lock (the candidate would start in
# restricted mode) and would keep an old candidate folder from being removed.
$running = @(Get-Process -Name CVMAnalytics -ErrorAction SilentlyContinue)
if ($running.Count -gt 0) {
    throw "CVMAnalytics is running (PID $($running.Id -join ', ')). Close it first: the app holds a runtime lock on its data folder."
}
# Inherited data-path overrides (dev-desktop.ps1 leaves CVM_DATA_DIR set in its
# terminal) would point the candidate at other data than the installed app uses.
$overrides = @(Get-ChildItem Env: | Where-Object { $_.Name -like "CVM_*" -or $_.Name -eq "SQLITE_PATH" } | ForEach-Object Name)
if ($overrides.Count -gt 0) {
    throw "This terminal sets $($overrides -join ', '), which would point the candidate at other data than the installed app uses. Open a new terminal and run this again."
}

# Remove the previous candidate, then download this one.
if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force }
$download = Join-Path $root "download"
foreach ($name in "publication-candidate", "publication-decision") {
    gh run download $runId --repo $repo --name $name --dir (Join-Path $download $name)
    if ($LASTEXITCODE -ne 0) { throw "Could not download $name from run $runId (see the gh error above)." }
}

# Verify the package against its checksum before anything is extracted.
$zip = @(Get-ChildItem -LiteralPath (Join-Path $download "publication-candidate") -File |
    Where-Object { $_.Name -match '^CVMAnalytics-windows-v(\d+\.\d+\.\d+)\.zip$' })
if ($zip.Count -ne 1) { throw "The candidate of run $runId must hold exactly one CVMAnalytics-windows-v<version>.zip." }
$zip = $zip[0]
$version = $zip.Name -replace '^CVMAnalytics-windows-v(.+)\.zip$', '$1'
$checksumFile = "$($zip.FullName).sha256"
if (-not (Test-Path -LiteralPath $checksumFile)) { throw "The candidate has no $($zip.Name).sha256. Refusing to open it." }
$expected = ((Get-Content -LiteralPath $checksumFile -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
$actual = (Get-FileHash -LiteralPath $zip.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) {
    throw "Checksum mismatch for $($zip.Name): the .sha256 file says $expected, the file is $actual. Refusing to open this candidate."
}

$decisionDir = Join-Path $download "publication-decision"
$facts = Get-Content -LiteralPath (Join-Path $decisionDir "facts.json") -Raw | ConvertFrom-Json
$decision = Get-Content -LiteralPath (Join-Path $decisionDir "decision.json") -Raw | ConvertFrom-Json
if ($decision.version -ne $version) { throw "The package is $version but run $runId decided $($decision.version). Refusing to open it." }

$appDir = Join-Path $root $version
Expand-Archive -LiteralPath $zip.FullName -DestinationPath $appDir
Remove-Item -LiteralPath $download -Recurse -Force
$exe = Join-Path $appDir "CVMAnalytics.exe"
if (-not (Test-Path -LiteralPath $exe)) { throw "The candidate has no CVMAnalytics.exe at its root." }

$dataDir = if ($env:CVMANALYTICS_DATA_DIR) { $env:CVMANALYTICS_DATA_DIR } else { Join-Path $env:USERPROFILE "Documents\CVMAnalytics" }
$kind = "$($decision.kind)" + $(if ($facts.dry_run) { ", dry run: never published" } else { "" })
Write-Host "[candidate] Run:      $($run.html_url) ($($run.status), $($run.event) on $($run.head_branch))"
Write-Host "[candidate] Version:  $version ($kind)"
Write-Host "[candidate] Commit:   $($facts.candidate_sha)"
Write-Host "[candidate] SHA-256:  $actual (matches the .sha256 file)"
Write-Host "[candidate] Folder:   $appDir"
Write-Warning "The candidate runs against your installed app's data in $dataDir, as the installed app would. Keep the installed app closed while you test; the installed app's own files are not touched."

$process = Start-Process -FilePath $exe -WorkingDirectory $appDir -PassThru
Write-Host "[candidate] Opened CVMAnalytics $version (PID $($process.Id))."
