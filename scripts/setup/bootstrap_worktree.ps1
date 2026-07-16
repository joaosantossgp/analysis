param(
  [string]$RepoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Require-Version {
  param(
    [string]$Command,
    [string]$Pattern,
    [int]$MinimumMajor,
    [int]$MinimumMinor,
    [string]$Requirement
  )

  $output = & $Command --version 2>&1
  if ($LASTEXITCODE -ne 0 -or $output -notmatch $Pattern) {
    throw "$Requirement is required; '$Command --version' did not return a supported version."
  }

  $major = [int]$Matches[1]
  $minor = [int]$Matches[2]
  if ($major -lt $MinimumMajor -or ($major -eq $MinimumMajor -and $minor -lt $MinimumMinor)) {
    throw "$Requirement is required; found $($output -join ' ')."
  }
}

$repoRootPath = (Resolve-Path -LiteralPath $RepoRoot).Path
$frontendPath = Join-Path $repoRootPath "apps\desktop-web"
$packageLockPath = Join-Path $frontendPath "package-lock.json"
$vitePath = Join-Path $frontendPath "node_modules\.bin\vite.cmd"

if (-not (Test-Path -LiteralPath $packageLockPath -PathType Leaf)) {
  throw "Missing frontend lockfile: $packageLockPath"
}

Write-Output "Worktree: $repoRootPath"
Require-Version -Command "node" -Pattern "^v?(\d+)\.(\d+)" -MinimumMajor 22 -MinimumMinor 0 -Requirement "Node.js 22+"
Require-Version -Command "python" -Pattern "^Python\s+(\d+)\.(\d+)" -MinimumMajor 3 -MinimumMinor 11 -Requirement "Python 3.11+"

if (-not (Test-Path -LiteralPath $vitePath -PathType Leaf)) {
  Write-Output "Frontend dependencies are missing; running npm ci."
  Push-Location $frontendPath
  try {
    & npm ci
    if ($LASTEXITCODE -ne 0) {
      throw "npm ci failed with exit code $LASTEXITCODE."
    }
  } finally {
    Pop-Location
  }
}

if (-not (Test-Path -LiteralPath $vitePath -PathType Leaf)) {
  throw "Local Vite resolution failed: $vitePath was not created by npm ci."
}

& $vitePath --version
if ($LASTEXITCODE -ne 0) {
  throw "Local Vite resolution failed with exit code $LASTEXITCODE."
}

Write-Output "Isolated worktree bootstrap is ready."
