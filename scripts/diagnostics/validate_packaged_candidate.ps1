[CmdletBinding()]
param(
  [ValidateSet('ValidateInputs','Run')][string]$Mode = 'Run',
  [Parameter(Mandatory)][string]$CandidateDir,
  [Parameter(Mandatory)][string]$EvidenceDir,
  [Parameter(Mandatory)][string]$SourceDataRoot,
  [int]$CdCvm = 9512,
  [int]$CdpPort = 9223
)

$ErrorActionPreference = 'Stop'

$repoRoot = (git rev-parse --show-toplevel).Trim()
$taskRoot = [IO.Path]::GetFullPath($EvidenceDir)
$candidateDir = [IO.Path]::GetFullPath($CandidateDir)
$sourceRoot = [IO.Path]::GetFullPath($SourceDataRoot)
$candidateExe = Join-Path $candidateDir 'CVMAnalytics.exe'
$zipPath = Join-Path $taskRoot 'CVMAnalytics-current-head.zip'
$fixtureRoot = Join-Path $taskRoot 'fixture'
$refreshFailureRoot = Join-Path $taskRoot 'fixture-refresh-failure'
$staged = Join-Path $taskRoot 'updater\staged'
$current = Join-Path $taskRoot 'updater\current'
$updaterLocalAppData = Join-Path $taskRoot 'updater\localappdata'
$uiResultsPath = Join-Path $taskRoot 'ui\ui-results.json'
$script:CleanupFailures = @()

function Resolve-ApprovedPath {
  param([Parameter(Mandatory)][string]$Path)

  $resolved = [IO.Path]::GetFullPath($Path)
  $cursor = $resolved
  while ($cursor) {
    if (Test-Path -LiteralPath $cursor) {
      $item = Get-Item -LiteralPath $cursor -Force
      if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "ReparsePoint path escape is not permitted: $cursor" }
    }
    $parent = Split-Path -Parent $cursor
    if (-not $parent -or $parent -eq $cursor) { break }
    $cursor = $parent
  }
  return $resolved
}

function Assert-Descendant {
  param([Parameter(Mandatory)][string]$Parent, [Parameter(Mandatory)][string]$Child)

  $parentPath = (Resolve-ApprovedPath -Path $Parent).TrimEnd('\', '/')
  $childPath = Resolve-ApprovedPath -Path $Child
  $prefix = $parentPath + [IO.Path]::DirectorySeparatorChar
  if (-not $childPath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Path escapes its approved parent: $childPath (parent: $parentPath)"
  }
}

function Stop-TrackedProcess {
  param([Parameter(Mandatory)][System.Diagnostics.Process]$Process, [Parameter(Mandatory)][string]$Label)
  if (-not $Process.HasExited) { Stop-Process -Id $Process.Id -Force -ErrorAction Stop }
  Wait-Process -Id $Process.Id -Timeout 15 -ErrorAction SilentlyContinue
  $Process.Refresh()
  if (-not $Process.HasExited) { throw "$Label process leaked after cleanup: $($Process.Id)" }
  return [ordered]@{ pid = $Process.Id; exit_code = $Process.ExitCode; exited = $true }
}

function Get-ExpectedCandidateIdentity {
  $versionText = Get-Content -LiteralPath (Join-Path $repoRoot 'desktop\__version__.py') -Raw
  if ($versionText -notmatch '__version__\s*=\s*["''](?<version>[^"'']+)["'']') { throw 'Cannot resolve expected candidate version' }
  $version = $matches.version
  $buildInfo = Join-Path $repoRoot 'desktop\_build_info.py'
  $buildCommit = $null
  if (Test-Path -LiteralPath $buildInfo) {
    $buildText = Get-Content -LiteralPath $buildInfo -Raw
    if ($buildText -match 'build_commit\s*=\s*["''](?<commit>[0-9a-fA-F]{7,64})["'']') { $buildCommit = $matches.commit.ToLowerInvariant() }
  }
  if (-not $buildCommit) { $buildCommit = (git rev-parse HEAD).Trim().ToLowerInvariant() }
  return [ordered]@{ version = $version; build_commit = $buildCommit }
}

function Inspect-CanonicalRuntimeLock {
  $lockPath = Join-Path $sourceRoot 'runtime.lock'
  $recordPath = Join-Path $taskRoot 'canonical-runtime-lock.json'
  Assert-Descendant -Parent $taskRoot -Child $recordPath
  $result = [ordered]@{ lock_path = $lockPath; exists = (Test-Path -LiteralPath $lockPath); checked_utc = [DateTime]::UtcNow.ToString('o'); owner = $null; live_owner = $false }
  if ($result.exists) {
    try { $result.owner = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json } catch { throw "Cannot parse canonical runtime.lock: $lockPath" }
    if ([IO.Path]::GetFullPath([string]$result.owner.data_dir) -ne $sourceRoot) { throw 'Canonical runtime.lock data_dir does not match SourceDataRoot' }
    if ($result.owner.pid) { $result.live_owner = [bool](Get-Process -Id ([int]$result.owner.pid) -ErrorAction SilentlyContinue) }
  }
  $result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $recordPath -Encoding UTF8
  if ($result.live_owner) { throw "Canonical data root is owned by live PID $($result.owner.pid); validation will not contend with it." }
  return $result
}

function Assert-MutationTargets {
  param([Parameter(Mandatory)][string[]]$Paths)
  foreach ($path in $Paths) { Assert-Descendant -Parent $taskRoot -Child $path }
}

function Assert-NoReparseTree {
  param([Parameter(Mandatory)][string]$Root)
  $rootPath = Resolve-ApprovedPath -Path $Root
  $taskPath = Resolve-ApprovedPath -Path $taskRoot
  if (-not $rootPath.Equals($taskPath, [StringComparison]::OrdinalIgnoreCase)) { Assert-Descendant -Parent $taskRoot -Child $rootPath }
  if (Test-Path -LiteralPath $Root) {
    foreach ($item in Get-ChildItem -LiteralPath $Root -Force -Recurse -ErrorAction Stop) {
      if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "ReparsePoint exists below evidence root: $($item.FullName)" }
    }
  }
}

function Prepare-RunAttempt {
  Assert-NoReparseTree -Root $taskRoot
  $attemptRoot = Join-Path $taskRoot ('attempts\' + [DateTime]::UtcNow.Ticks + '-' + [guid]::NewGuid().ToString('N'))
  $knownOutputs = @('CVMAnalytics-current-head.zip','fixture','fixture-refresh-failure','updater','ui','refresh-failure-ui','localappdata-diagnostic','localappdata-ui','localappdata-refresh-failure','source-before-manifest.json','source-after-manifest.json','fixture-before-manifest.json','fixture-after-manifest.json','refresh-failure-before-manifest.json','refresh-failure-after-manifest.json','refresh_failure_sql.json','evidence-summary.json','evidence-summary-fallback.json','canonical-runtime-lock.json','diagnostic.stdout.log','diagnostic.stderr.log')
  foreach ($name in $knownOutputs) {
    $source = Join-Path $taskRoot $name
    if (Test-Path -LiteralPath $source) {
      $destination = Join-Path $attemptRoot $name
      Assert-MutationTargets -Paths @($source,$destination)
      New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
      Move-Item -LiteralPath $source -Destination $destination -Force
    }
  }
  Assert-MutationTargets -Paths @($fixtureRoot,$refreshFailureRoot)
  if ((Test-Path -LiteralPath $fixtureRoot) -or (Test-Path -LiteralPath $refreshFailureRoot)) { throw 'Fresh fixture roots could not be established for this attempt' }
}

function Register-SecondaryFailure {
  param([Parameter(Mandatory)][hashtable]$Evidence, [Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)]$ErrorRecord)
  if (-not $Evidence.secondary_failures) { $Evidence.secondary_failures = @() }
  $Evidence.secondary_failures += [ordered]@{ name = $Name; message = $ErrorRecord.Exception.Message }
}

function Invoke-RecordedStep {
  param([Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][scriptblock]$Action, [Parameter(Mandatory)][AllowEmptyCollection()][System.Collections.ArrayList]$Results)
  $started = [DateTime]::UtcNow
  $bodyFailure = $null
  try {
    $value = & $Action
    [void]$Results.Add([ordered]@{ name = $Name; status = 'pass'; started_utc = $started.ToString('o'); duration_ms = [int]([DateTime]::UtcNow - $started).TotalMilliseconds; pid = $value.pid; exit_code = $value.exit_code })
    return $value
  } catch {
    [void]$Results.Add([ordered]@{ name = $Name; status = 'failed'; started_utc = $started.ToString('o'); duration_ms = [int]([DateTime]::UtcNow - $started).TotalMilliseconds; pid = $_.Exception.Data['node_pid']; exit_code = $_.Exception.Data['node_exit_code']; stdout = $_.Exception.Data['node_stdout']; stderr = $_.Exception.Data['node_stderr']; error = $_.Exception.Message })
    throw
  }
}

function Write-EvidenceSummary {
  param([Parameter(Mandatory)][hashtable]$Evidence)
  $artifactInventory = @()
  if (Test-Path -LiteralPath $taskRoot) {
    foreach ($artifact in Get-ChildItem -LiteralPath $taskRoot -File -Recurse -ErrorAction SilentlyContinue | Sort-Object FullName) {
      Assert-Descendant -Parent $taskRoot -Child $artifact.FullName
      $artifactInventory += [ordered]@{ path = $artifact.FullName; bytes = $artifact.Length; sha256 = (Get-FileHash -LiteralPath $artifact.FullName -Algorithm SHA256).Hash }
    }
  }
  $Evidence.artifact_inventory = $artifactInventory
  $summaryPath = Join-Path $taskRoot 'evidence-summary.json'
  Assert-MutationTargets -Paths @($summaryPath)
  $Evidence | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $summaryPath -Encoding UTF8
}

function Assert-ExistingDescendant {
  param([Parameter(Mandatory)][string]$Parent, [Parameter(Mandatory)][string]$Child, [Parameter(Mandatory)][string]$Label)

  Assert-Descendant -Parent $Parent -Child $Child
  if (-not (Test-Path -LiteralPath $Child)) { throw "$Label does not exist: $Child" }
}

function Write-FileManifest {
  param([Parameter(Mandatory)][string]$Root, [Parameter(Mandatory)][string[]]$RelativePaths, [Parameter(Mandatory)][string]$OutputPath)

  Assert-Descendant -Parent $taskRoot -Child $OutputPath
  $rows = foreach ($relativePath in $RelativePaths) {
    $fullPath = Join-Path $Root $relativePath
    if (-not (Test-Path -LiteralPath $fullPath)) {
      [ordered]@{ path = $relativePath.Replace('\', '/'); status = 'missing' }
      continue
    }
    $files = @(Get-ChildItem -LiteralPath $fullPath -File -Recurse | Sort-Object FullName)
    if ($files.Count -eq 0) { [ordered]@{ path = $relativePath.Replace('\','/'); status = 'empty' }; continue }
    foreach ($file in $files) {
      $relative = [IO.Path]::GetRelativePath($Root, $file.FullName).Replace('\', '/')
      [ordered]@{
        path = $relative
        status = 'present'
        length = $file.Length
        sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
      }
    }
  }
  @($rows | Sort-Object path) | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
  return (Get-Content -LiteralPath $OutputPath -Raw)
}

function Backup-SqliteDatabase {
  param([Parameter(Mandatory)][string]$Source, [Parameter(Mandatory)][string]$Destination)

  Assert-ExistingDescendant -Parent $sourceRoot -Child $Source -Label 'Source database'
  Assert-Descendant -Parent $fixtureRoot -Child $Destination
  $destinationDir = Split-Path -Parent $Destination
  New-Item -ItemType Directory -Force -Path $destinationDir | Out-Null
  & python -c "import sqlite3,sys,pathlib; s,d=map(pathlib.Path,sys.argv[1:]); d.parent.mkdir(parents=True,exist_ok=True); a=sqlite3.connect(f'file:{s.as_posix()}?mode=ro',uri=True); b=sqlite3.connect(d); a.backup(b); b.close(); a.close()" $Source $Destination
  if ($LASTEXITCODE -ne 0) { throw "SQLite backup failed: $Source" }
}

function New-ChildEnvironment {
  param([Parameter(Mandatory)][string]$DataRoot, [Parameter(Mandatory)][string]$LocalAppData)

  return @{
    CVMANALYTICS_DATA_DIR = $DataRoot
    CVM_DATA_DIR = $DataRoot
    CVM_INPUT_DIR = (Join-Path $DataRoot 'input')
    CVM_REPORTS_DIR = (Join-Path $DataRoot 'output\reports')
    CVM_METADATA_DIR = (Join-Path $DataRoot 'metadata')
    CVM_DB_DIR = (Join-Path $DataRoot 'db')
    SQLITE_PATH = (Join-Path $DataRoot 'db\cvm_financials.db')
    CVM_CANONICAL_ACCOUNTS_PATH = (Join-Path $candidateDir '_internal\data\import\canonical_accounts.csv')
    CVM_ACCOUNT_DICTIONARY_PATH = (Join-Path $DataRoot 'cvm_account_dictionary.csv')
    CVM_COMPANY_UNIVERSE_SNAPSHOT_PATH = (Join-Path $DataRoot 'metadata\b3_market_cap_universe_snapshot.csv')
    CVM_ENERGY_KPI_DB = (Join-Path $DataRoot 'db\energy_kpis.db')
    CVM_ENERGY_KPI_RAW_DIR = (Join-Path $DataRoot 'raw\energy')
    CVM_ENERGY_HOURLY_HOT_COLD_MANIFEST = (Join-Path $DataRoot 'analytics\energy\ccee_plant_generation_hourly\manifest.json')
    CVM_NEWS_DB = (Join-Path $DataRoot 'db\news.db')
    CVM_OUTPUT_DIR = (Join-Path $DataRoot 'output')
    CVM_LOG_DIR = (Join-Path $DataRoot 'logs')
    CVM_CACHE_DIR = (Join-Path $DataRoot 'cache')
    CVM_ONBOARDING_STATE_PATH = (Join-Path $DataRoot 'onboarding_state.json')
    DATABASE_URL = ''
    LOCALAPPDATA = $LocalAppData
    CVM_CATALOG_URL = 'http://127.0.0.1:9/cad.csv'
    HTTP_PROXY = 'http://127.0.0.1:9'
    HTTPS_PROXY = 'http://127.0.0.1:9'
    ALL_PROXY = 'http://127.0.0.1:9'
    NO_PROXY = '127.0.0.1,localhost'
  }
}

function New-CandidateZip {
  Assert-Descendant -Parent $taskRoot -Child $zipPath
  Compress-Archive -Path (Join-Path $candidateDir '*') -DestinationPath $zipPath -CompressionLevel Optimal -Force
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $archive = [IO.Compression.ZipFile]::OpenRead((Resolve-Path $zipPath).Path)
  try {
    $roots = @($archive.Entries | ForEach-Object { ($_.FullName -replace '\\','/').Split('/')[0] } | Where-Object { $_ } | Sort-Object -Unique)
    if (Compare-Object @('CVMAnalytics.exe','_internal') $roots) { throw "Unexpected ZIP roots: $($roots -join ', ')" }
    if (-not ($archive.Entries.FullName -contains 'CVMAnalytics.exe')) { throw 'CVMAnalytics.exe is not at the ZIP root' }
    return [ordered]@{ path = $zipPath; entries = $archive.Entries.Count; bytes = (Get-Item $zipPath).Length; sha256 = (Get-FileHash $zipPath -Algorithm SHA256).Hash }
  } finally { $archive.Dispose() }
}

function Invoke-IsolatedDiagnostic {
  param([Parameter(Mandatory)][hashtable]$ChildEnvironment, [Parameter(Mandatory)][hashtable]$ExpectedIdentity)

  $started = [DateTime]::UtcNow
  $stdout = Join-Path $taskRoot 'diagnostic.stdout.log'
  $stderr = Join-Path $taskRoot 'diagnostic.stderr.log'
  Assert-MutationTargets -Paths @($stdout, $stderr, $ChildEnvironment.LOCALAPPDATA, $ChildEnvironment.CVM_OUTPUT_DIR, $ChildEnvironment.CVM_LOG_DIR, $ChildEnvironment.CVM_CACHE_DIR, $ChildEnvironment.CVM_DB_DIR, $ChildEnvironment.CVM_METADATA_DIR)
  $p = Start-Process $candidateExe -ArgumentList '--diagnose-runtime','--non-interactive' -Environment $ChildEnvironment -PassThru -Wait -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
  if ($p.ExitCode -ne 0) { throw "Diagnostic failed: $($p.ExitCode)" }
  $diagnosticText = (Get-Content -LiteralPath $stdout -Raw) + (Get-Content -LiteralPath $stderr -Raw)
  $diagnosticLogs = Get-ChildItem -LiteralPath (Join-Path $fixtureRoot 'logs') -File -Recurse -ErrorAction SilentlyContinue | Get-Content -Raw -ErrorAction SilentlyContinue
  $diagnosticText += ($diagnosticLogs -join [Environment]::NewLine)
  foreach ($required in @('frozen', "version: $($ExpectedIdentity.version)", $fixtureRoot, $ChildEnvironment.LOCALAPPDATA)) {
    if ($diagnosticText -notmatch [regex]::Escape($required)) { throw "Diagnostic evidence is missing: $required" }
  }
  $canonicalDocuments = Join-Path $env:USERPROFILE 'Documents\CVMAnalytics'
  if ($diagnosticText -match [regex]::Escape($canonicalDocuments)) { throw 'Diagnostic leaked the canonical Documents root' }
  return [ordered]@{ status = 'pass'; started_utc = $started.ToString('o'); duration_ms = [int]([DateTime]::UtcNow - $started).TotalMilliseconds; pid = $p.Id; exit_code = $p.ExitCode; stdout = $stdout; stderr = $stderr; version = $ExpectedIdentity.version; build_sha_validation = 'deferred to get_app_status because --diagnose-runtime does not emit build_commit' }
}

function Wait-ForCdpBridge {
  param([Parameter(Mandatory)][System.Diagnostics.Process]$Process, [Parameter(Mandatory)][string]$OutputDir, [Parameter(Mandatory)][long]$ProcessStartMs, [Parameter(Mandatory)][hashtable]$ExpectedIdentity, [switch]$ReadinessOnly)
  Assert-Descendant -Parent $taskRoot -Child $OutputDir
  $deadline = (Get-Date).AddSeconds(60)
  do {
    try { $cdp = Invoke-RestMethod "http://127.0.0.1:$CdpPort/json/version"; break }
    catch { Start-Sleep -Milliseconds 250 }
  } while ((Get-Date) -lt $deadline -and -not $Process.HasExited)
  if (-not $cdp) { throw 'CDP readiness timeout' }
  $arguments = @('--cdp-url', "http://127.0.0.1:$CdpPort", '--output-dir', $OutputDir, '--cd-cvm', $CdCvm, '--process-start-ms', $ProcessStartMs, '--expected-version', $ExpectedIdentity.version, '--expected-build-sha', $ExpectedIdentity.build_commit)
  if ($ReadinessOnly) { $arguments += '--readiness-only' }
  $nodeStdout = Join-Path $OutputDir 'node.stdout.log'; $nodeStderr = Join-Path $OutputDir 'node.stderr.log'
  Assert-MutationTargets -Paths @($nodeStdout,$nodeStderr)
  $node = Start-Process (Get-Command node).Source -ArgumentList (@((Join-Path $repoRoot 'scripts\diagnostics\validate_packaged_ui.cjs')) + $arguments) -PassThru -Wait -WindowStyle Hidden -RedirectStandardOutput $nodeStdout -RedirectStandardError $nodeStderr
  if ($node.ExitCode -ne 0) { $failure = [System.Exception]::new("CDP harness failed: $($node.ExitCode) (PID $($node.Id))"); $failure.Data['node_pid'] = $node.Id; $failure.Data['node_exit_code'] = $node.ExitCode; $failure.Data['node_stdout'] = $nodeStdout; $failure.Data['node_stderr'] = $nodeStderr; throw $failure }
  return [ordered]@{ pid = $node.Id; exit_code = $node.ExitCode; stdout = $nodeStdout; stderr = $nodeStderr }
}

function Invoke-PackagedUi {
  param([Parameter(Mandatory)][hashtable]$ChildEnvironment, [Parameter(Mandatory)][hashtable]$ExpectedIdentity)

  $uiEnv = $ChildEnvironment.Clone()
  $started = [DateTime]::UtcNow
  $uiEnv.LOCALAPPDATA = Join-Path $taskRoot 'localappdata-ui'
  $uiEnv.WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$CdpPort --remote-allow-origins=* --proxy-server=http://127.0.0.1:9 --proxy-bypass-list=127.0.0.1;localhost"
  Assert-MutationTargets -Paths @($uiEnv.LOCALAPPDATA, $uiEnv.CVM_OUTPUT_DIR, $uiEnv.CVM_LOG_DIR, $uiEnv.CVM_CACHE_DIR, $uiEnv.CVM_DB_DIR, $uiEnv.CVM_METADATA_DIR, (Join-Path $taskRoot 'ui'))
  $processStartMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
  $p = Start-Process $candidateExe -Environment $uiEnv -PassThru -WindowStyle Hidden
  try {
    $outputDir = Join-Path $taskRoot 'ui'
    $nodeChild = Wait-ForCdpBridge -Process $p -OutputDir $outputDir -ProcessStartMs $processStartMs -ExpectedIdentity $ExpectedIdentity
    if (-not (Test-Path -LiteralPath $uiResultsPath)) { throw "Missing UI results: $uiResultsPath" }
    $result = [ordered]@{ status = 'pass'; pid = $p.Id; node_child = $nodeChild; results = $uiResultsPath; started_utc = $started.ToString('o'); duration_ms = 0 }
  } catch { $bodyFailure = $_; throw } finally {
    try { $cleanup = Stop-TrackedProcess -Process $p -Label 'Packaged UI' } catch { if ($bodyFailure) { $script:CleanupFailures += @{ name = 'packaged_ui_cleanup'; message = $_.Exception.Message } } else { throw } }
  }
  $result.duration_ms = [int]([DateTime]::UtcNow - $started).TotalMilliseconds
  $result.cleanup = $cleanup
  return $result
}

function Test-RefreshFailureStartup {
  param([Parameter(Mandatory)][hashtable]$ExpectedIdentity)
  Assert-Descendant -Parent $taskRoot -Child $refreshFailureRoot
  $failureEnv = New-ChildEnvironment -DataRoot $refreshFailureRoot -LocalAppData (Join-Path $taskRoot 'localappdata-refresh-failure')
  $started = [DateTime]::UtcNow
  $failureEnv.WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$CdpPort --remote-allow-origins=* --proxy-server=http://127.0.0.1:9 --proxy-bypass-list=127.0.0.1;localhost"
  Assert-MutationTargets -Paths @($failureEnv.LOCALAPPDATA, $failureEnv.CVM_OUTPUT_DIR, $failureEnv.CVM_LOG_DIR, $failureEnv.CVM_CACHE_DIR, $failureEnv.CVM_DB_DIR, $failureEnv.CVM_METADATA_DIR, (Join-Path $taskRoot 'refresh-failure-ui'))
  $processStartMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
  $p = Start-Process $candidateExe -Environment $failureEnv -PassThru -WindowStyle Hidden
  $bodyFailure = $null
  try {
    $nodeChild = Wait-ForCdpBridge -Process $p -OutputDir (Join-Path $taskRoot 'refresh-failure-ui') -ProcessStartMs $processStartMs -ExpectedIdentity $ExpectedIdentity -ReadinessOnly
    Start-Sleep -Seconds 13
    if ($p.HasExited) { throw "Refresh-failure candidate exited early: $($p.ExitCode)" }
    $state = & python -c "import sqlite3,sys,json; c=sqlite3.connect(sys.argv[1]); row=c.execute('select cnpj from companies where cd_cvm=?',(int(sys.argv[2]),)).fetchone(); refresh=c.execute(\"select value from app_settings where key='metadata_last_successful_refresh'\").fetchone(); print(json.dumps({'exists':row is not None,'cnpj':None if row is None else row[0],'metadata_last_successful_refresh':None if refresh is None else refresh[0]})); c.close()" (Join-Path $refreshFailureRoot 'db\cvm_financials.db') $CdCvm
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect refresh-failure fixture' }
    if (-not (($state | ConvertFrom-Json).exists)) { throw 'Representative company row disappeared during refresh-failure observation' }
    if ((($state | ConvertFrom-Json).cnpj) -ne $null) { throw 'Offline refresh failure unexpectedly restored the fixture CNPJ' }
    if ((($state | ConvertFrom-Json).metadata_last_successful_refresh) -ne $null) { throw 'Offline refresh failure unexpectedly persisted metadata_last_successful_refresh' }
    $result = [ordered]@{ status = 'pass'; pid = $p.Id; node_child = $nodeChild; stayed_alive_after_seconds = 13; state = ($state | ConvertFrom-Json); started_utc = $started.ToString('o'); duration_ms = 0 }
  } catch { $bodyFailure = $_; throw } finally {
    try { $cleanup = Stop-TrackedProcess -Process $p -Label 'Refresh-failure packaged UI' } catch { if ($bodyFailure) { $script:CleanupFailures += @{ name = 'refresh_failure_cleanup'; message = $_.Exception.Message } } else { throw } }
  }
  $result.duration_ms = [int]([DateTime]::UtcNow - $started).TotalMilliseconds
  $result.cleanup = $cleanup
  return $result
}

function Test-WorkbookOpen {
  $uiResults = Get-Content -LiteralPath $uiResultsPath -Raw | ConvertFrom-Json
  $excelPath = [IO.Path]::GetFullPath($uiResults.bridge_results.export_company_excel.result.file_path)
  Assert-Descendant -Parent (Join-Path $fixtureRoot 'output') -Child $excelPath
  if (-not (Test-Path -LiteralPath $excelPath)) { throw "Export workbook is absent: $excelPath" }
  $openPyxl = & python -c "import openpyxl,sys,json; p=sys.argv[1]; w=openpyxl.load_workbook(p,data_only=False,read_only=True); print(json.dumps({'sheets':w.sheetnames,'formulas':sum(1 for s in w for row in s.iter_rows() for c in row if isinstance(c.value,str) and c.value.startswith('='))})); w.close()" $excelPath
  if ($LASTEXITCODE -ne 0) { throw 'openpyxl could not read the exported workbook' }
  $excel = $null
  $book = $null
  $comNeedsValidation = $null
  $readOnlyOpenSucceeded = $false
  try { $excel = New-Object -ComObject Excel.Application } catch [Runtime.InteropServices.COMException] { if ($_.Exception.HResult -eq 0x80040154) { $comNeedsValidation = $_.Exception.Message } else { throw } }
  if ($excel) {
    try { $excel.DisplayAlerts = $false; $book = $excel.Workbooks.Open($excelPath, 0, $true); $readOnlyOpenSucceeded = $true; $book.Close($false) }
    finally {
      if ($book) { [Runtime.InteropServices.Marshal]::FinalReleaseComObject($book) | Out-Null }
      $excel.Quit()
      [Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel) | Out-Null
    }
  }
  $openPyxlEvidence = $openPyxl | ConvertFrom-Json
  return [ordered]@{
    path = $excelPath
    sha256 = (Get-FileHash $excelPath -Algorithm SHA256).Hash
    file_size_bytes = (Get-Item -LiteralPath $excelPath).Length
    sheets = @($openPyxlEvidence.sheets)
    formula_count = [int]$openPyxlEvidence.formulas
    com_activation = if ($excel) { 'activated' } else { 'needs_validation_class_not_registered' }
    com_needs_validation = $comNeedsValidation
    read_only_open_succeeded = $readOnlyOpenSucceeded
    no_repair_prompt_observable = 'Excel alerts were suppressed; successful read-only open means no repair prompt was observable under automation, not stronger repair detection.'
  }
}

function Invoke-ScratchUpdaterTest {
  $started = [DateTime]::UtcNow
  $protected = @('data','output','logs','cache','tmp','backup','versions','update_rollback')
  $rollbackRoot = Join-Path $updaterLocalAppData 'CVMAnalytics\update_rollback'
  Assert-MutationTargets -Paths @($staged, $current, $updaterLocalAppData, (Join-Path $staged 'CVMAnalytics.exe'), (Join-Path $current 'CVMAnalytics.exe'), (Join-Path $staged '_internal'), (Join-Path $current '_internal'), (Join-Path $updaterLocalAppData 'CVMAnalytics'), $rollbackRoot)
  foreach ($name in $protected) { Assert-MutationTargets -Paths @((Join-Path $current $name), (Join-Path $current "$name\sentinel.txt")) }
  foreach ($root in @($staged, $current)) { New-Item -ItemType Directory -Force -Path (Join-Path $root '_internal') | Out-Null }
  $sourceTemplate = @'
using System;
using System.IO;
public static class {0} {{ [STAThread] public static void Main() {{ File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "relaunch.marker"), "{1}"); }} }}
'@
  Add-Type -TypeDefinition ($sourceTemplate -f 'OldProgram','old') -OutputAssembly (Join-Path $current 'CVMAnalytics.exe') -OutputType ConsoleApplication
  Add-Type -TypeDefinition ($sourceTemplate -f 'StagedProgram','staged') -OutputAssembly (Join-Path $staged 'CVMAnalytics.exe') -OutputType ConsoleApplication
  Set-Content -LiteralPath (Join-Path $current '_internal\version.txt') -Value 'old'
  Set-Content -LiteralPath (Join-Path $staged '_internal\version.txt') -Value 'staged'
  $oldExecutableSha256 = (Get-FileHash (Join-Path $current 'CVMAnalytics.exe') -Algorithm SHA256).Hash
  $oldInternalSha256 = (Get-FileHash (Join-Path $current '_internal\version.txt') -Algorithm SHA256).Hash
  foreach ($name in $protected) { New-Item -ItemType Directory -Force -Path (Join-Path $current $name) | Out-Null; Set-Content -LiteralPath (Join-Path $current "$name\sentinel.txt") -Value $name }
  $before = @{}; foreach ($name in $protected) { $before[$name] = (Get-FileHash (Join-Path $current "$name\sentinel.txt") -Algorithm SHA256).Hash }
  $helper = (Resolve-Path (Join-Path $repoRoot 'desktop\update_helper.ps1')).Path
  $helperEnv = @{ LOCALAPPDATA = $updaterLocalAppData }
  $p = Start-Process powershell.exe -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$helper,'-New',$staged,'-Current',$current) -Environment $helperEnv -PassThru -Wait -WindowStyle Hidden
  if ($p.ExitCode -ne 0) { throw "Updater helper failed: $($p.ExitCode)" }
  if (-not (Test-Path -LiteralPath (Join-Path $current 'relaunch.marker'))) { throw 'Updater did not relaunch the staged executable' }
  if ((Get-Content -LiteralPath (Join-Path $current '_internal\version.txt') -Raw).Trim() -ne 'staged') { throw 'Updater did not copy staged _internal files' }
  Assert-Descendant -Parent $taskRoot -Child $rollbackRoot
  $rollback = Get-ChildItem -LiteralPath $rollbackRoot -Directory -ErrorAction SilentlyContinue | Where-Object { (Test-Path -LiteralPath (Join-Path $_.FullName 'CVMAnalytics.exe')) -and (Test-Path -LiteralPath (Join-Path $_.FullName '_internal\version.txt')) } | Select-Object -First 1
  if (-not $rollback) { throw 'Updater rollback is missing the old executable or rollback _internal tree' }
  $rollbackExecutableSha256 = (Get-FileHash (Join-Path $rollback.FullName 'CVMAnalytics.exe') -Algorithm SHA256).Hash
  $rollbackInternalSha256 = (Get-FileHash (Join-Path $rollback.FullName '_internal\version.txt') -Algorithm SHA256).Hash
  if ($oldExecutableSha256 -ne $rollbackExecutableSha256) { throw 'Updater rollback executable does not match the old executable' }
  if ($oldInternalSha256 -ne $rollbackInternalSha256) { throw 'Updater rollback _internal does not match the old _internal tree' }
  if ((Get-Content -LiteralPath (Join-Path $rollback.FullName '_internal\version.txt') -Raw).Trim() -ne 'old') { throw 'Updater rollback _internal did not preserve the old version' }
  $helperLog = Join-Path $updaterLocalAppData 'CVMAnalytics\update_error.log'
  if (-not (Test-Path -LiteralPath $helperLog) -or (Get-Content -LiteralPath $helperLog -Raw) -notmatch 'relaunch issued OK') { throw 'Updater helper did not record a successful relaunch' }
  foreach ($name in $protected) { if ($before[$name] -ne (Get-FileHash (Join-Path $current "$name\sentinel.txt") -Algorithm SHA256).Hash) { throw "Updater changed protected directory: $name" } }
  return [ordered]@{ status = 'pass'; started_utc = $started.ToString('o'); duration_ms = [int]([DateTime]::UtcNow - $started).TotalMilliseconds; pid = $p.Id; exit_code = $p.ExitCode; protected_directories = $protected; rollback_path = $rollback.FullName; old_executable_sha256 = $oldExecutableSha256; rollback_executable_sha256 = $rollbackExecutableSha256; old_internal_sha256 = $oldInternalSha256; rollback_internal_sha256 = $rollbackInternalSha256 }
}

function Compare-PreservationManifest {
  param([Parameter(Mandatory)][string]$BeforePath, [Parameter(Mandatory)][string]$AfterPath)
  $beforeBytes = [IO.File]::ReadAllBytes($BeforePath)
  $afterBytes = [IO.File]::ReadAllBytes($AfterPath)
  if ($beforeBytes.Length -ne $afterBytes.Length -or [Convert]::ToBase64String($beforeBytes) -ne [Convert]::ToBase64String($afterBytes)) { throw 'Canonical source preservation manifest bytes changed' }
}

function Classify-FixtureManifestChanges {
  param([Parameter(Mandatory)][string]$BeforePath, [Parameter(Mandatory)][string]$AfterPath, [ValidateSet('main','refresh-failure')][string]$Policy = 'main')
  $before = Get-Content -LiteralPath $BeforePath -Raw | ConvertFrom-Json
  $after = Get-Content -LiteralPath $AfterPath -Raw | ConvertFrom-Json
  $beforeByPath = @{}; foreach ($row in @($before)) { $beforeByPath[$row.path] = $row }
  $afterByPath = @{}; foreach ($row in @($after)) { $afterByPath[$row.path] = $row }
  $changes = @()
  foreach ($row in @($after)) {
    $prior = $beforeByPath[$row.path]
    if (-not $prior -or $prior.status -ne $row.status -or $prior.sha256 -ne $row.sha256 -or $prior.length -ne $row.length) {
      $allowed = if ($Policy -eq 'main') { $row.path -like 'output/*' -or $row.path -like 'logs/*' -or $row.path -like 'cache/*' } else { $row.path -like 'logs/*' -or $row.path -like 'cache/*' } # refresh-failure only permits logs/cache
      $classification = if ($allowed) { 'expected_fixture_runtime_change' } elseif ($row.path -like 'db/*' -or $row.path -like 'metadata/*') { 'unexpected_fixture_database_change' } else { 'unexpected_fixture_change' }
      $changes += [ordered]@{ path = $row.path; classification = $classification; before = $prior; after = $row }
    }
  }
  foreach ($prior in @($before)) {
    $materializedOptionalRoot = $prior.status -in @('missing','empty') -and ($prior.path -in @('output','logs','cache')) -and @($afterByPath.Keys | Where-Object { $_ -like "$($prior.path)/*" }).Count -gt 0
    if (-not $afterByPath.ContainsKey($prior.path) -and -not $materializedOptionalRoot) { $changes += [ordered]@{ path = $prior.path; classification = 'before-only'; before = $prior; after = $null } }
  }
  if ($changes | Where-Object { $_.classification -notlike 'expected_*' }) { throw 'Fixture changed outside the narrow output/log/cache allowance' }
  return $changes
}

function Test-FixturePolicy {
  param([Parameter(Mandatory)][string]$BeforePath, [Parameter(Mandatory)][string]$AfterPath, [Parameter(Mandatory)][string]$Policy)
  return Classify-FixtureManifestChanges -BeforePath $BeforePath -AfterPath $AfterPath -Policy $Policy
}

function New-Fixture {
  Assert-MutationTargets -Paths @($fixtureRoot, (Join-Path $fixtureRoot 'db'), (Join-Path $fixtureRoot 'metadata'), (Join-Path $fixtureRoot 'output'), (Join-Path $fixtureRoot 'logs'), (Join-Path $fixtureRoot 'cache'), $refreshFailureRoot, (Join-Path $refreshFailureRoot 'db'), (Join-Path $refreshFailureRoot 'output'), (Join-Path $refreshFailureRoot 'logs'), (Join-Path $refreshFailureRoot 'cache'))
  New-Item -ItemType Directory -Force -Path $fixtureRoot | Out-Null
  Backup-SqliteDatabase -Source (Join-Path $sourceRoot 'db\cvm_financials.db') -Destination (Join-Path $fixtureRoot 'db\cvm_financials.db')
  Backup-SqliteDatabase -Source (Join-Path $sourceRoot 'db\energy_kpis.db') -Destination (Join-Path $fixtureRoot 'db\energy_kpis.db')
  $marketCap = Join-Path $sourceRoot 'metadata\b3_market_cap_universe_snapshot.csv'
  if (Test-Path -LiteralPath $marketCap) { New-Item -ItemType Directory -Force -Path (Join-Path $fixtureRoot 'metadata') | Out-Null; Copy-Item -LiteralPath $marketCap -Destination (Join-Path $fixtureRoot 'metadata\b3_market_cap_universe_snapshot.csv') }
  $company = & python -c "import sqlite3,sys,json; c=sqlite3.connect(sys.argv[1]); r=c.execute('select cnpj from companies where cd_cvm=?',(int(sys.argv[2]),)).fetchone(); print(json.dumps({'exists':r is not None,'cnpj':None if r is None else r[0]})); c.close()" (Join-Path $fixtureRoot 'db\cvm_financials.db') $CdCvm | ConvertFrom-Json
  if (-not $company.exists) { throw "Representative company row is missing from fixture: $CdCvm" }
  Copy-Item -LiteralPath $fixtureRoot -Destination $refreshFailureRoot -Recurse -Force
  $fixtureSql = @("UPDATE companies SET cnpj = NULL WHERE cd_cvm = ?", "DELETE FROM app_settings WHERE key = 'metadata_last_successful_refresh'")
  $fixtureSql | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRoot 'refresh_failure_sql.json') -Encoding UTF8
  & python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('update companies set cnpj=NULL where cd_cvm=?',(int(sys.argv[2]),)); c.execute(\"delete from app_settings where key='metadata_last_successful_refresh'\"); c.commit(); c.close()" (Join-Path $refreshFailureRoot 'db\cvm_financials.db') $CdCvm
  if ($LASTEXITCODE -ne 0) { throw 'Could not prepare refresh-failure fixture' }
}

function Test-InputContract {
  $scratchRoot = Join-Path $repoRoot 'scratch'
  $distRoot = Join-Path $repoRoot 'dist'
  Assert-Descendant -Parent $scratchRoot -Child $taskRoot
  Assert-Descendant -Parent $distRoot -Child $candidateDir
  Assert-ExistingDescendant -Parent $candidateDir -Child $candidateExe -Label 'Candidate executable'
  Assert-ExistingDescendant -Parent $candidateDir -Child (Join-Path $candidateDir '_internal\data\import\canonical_accounts.csv') -Label 'Bundled canonical mapping'
  if (-not (Test-Path -LiteralPath $sourceRoot)) { throw "Explicit source data root does not exist: $sourceRoot" }
  foreach ($target in @($zipPath, $fixtureRoot, $refreshFailureRoot, $staged, $current, $updaterLocalAppData, $uiResultsPath)) { Assert-Descendant -Parent $taskRoot -Child $target }
  [ordered]@{ mode = $Mode; repo_root = $repoRoot; task_root = $taskRoot; candidate_dir = $candidateDir; source_root = $sourceRoot; candidate_exe = $candidateExe } | ConvertTo-Json -Depth 4
}

Test-InputContract
if ($Mode -eq 'ValidateInputs') { exit 0 }

New-Item -ItemType Directory -Force -Path $taskRoot | Out-Null
Assert-NoReparseTree -Root $taskRoot
$runStarted = [DateTime]::UtcNow
$stepResults = [System.Collections.ArrayList]@()
$evidence = @{ harness_commit_sha = (git rev-parse HEAD).Trim(); started_utc = $runStarted.ToString('o'); status = 'running'; primary_failure = $null; step_results = $stepResults }
$sourcePaths = @('input','raw','source_snapshots','db\cvm_financials.db','db\energy_kpis.db')
$sourceBefore = Join-Path $taskRoot 'source-before-manifest.json'
$sourceAfter = Join-Path $taskRoot 'source-after-manifest.json'
$fixtureBefore = Join-Path $taskRoot 'fixture-before-manifest.json'
$fixtureAfter = Join-Path $taskRoot 'fixture-after-manifest.json'
$refreshBefore = Join-Path $taskRoot 'refresh-failure-before-manifest.json'
$refreshAfter = Join-Path $taskRoot 'refresh-failure-after-manifest.json'
Assert-MutationTargets -Paths @($sourceBefore,$sourceAfter,$fixtureBefore,$fixtureAfter,$refreshBefore,$refreshAfter,(Join-Path $taskRoot 'refresh_failure_sql.json'),(Join-Path $taskRoot 'evidence-summary.json'),(Join-Path $taskRoot 'ui\ui-results.json'),(Join-Path $taskRoot 'ui\console-errors.json'),(Join-Path $taskRoot 'ui\network-log.json'),(Join-Path $taskRoot 'refresh-failure-ui\ui-results.json'),(Join-Path $taskRoot 'refresh-failure-ui\console-errors.json'),(Join-Path $taskRoot 'refresh-failure-ui\network-log.json'))
$primaryFailure = $null
try {
  Invoke-RecordedStep -Name 'attempt_preparation' -Results $stepResults -Action { Prepare-RunAttempt; @{ exit_code = 0 } } | Out-Null
  if (Get-Process -Name CVMAnalytics -ErrorAction SilentlyContinue) { throw 'A CVMAnalytics process is active; validation will not hash or contend with canonical data.' }
  $expectedIdentity = Invoke-RecordedStep -Name 'candidate_identity' -Results $stepResults -Action { Get-ExpectedCandidateIdentity }
  $runtimeLock = Invoke-RecordedStep -Name 'runtime_lock' -Results $stepResults -Action { Inspect-CanonicalRuntimeLock }
  Invoke-RecordedStep -Name 'source_before_manifest' -Results $stepResults -Action { Write-FileManifest -Root $sourceRoot -RelativePaths $sourcePaths -OutputPath $sourceBefore | Out-Null; @{ exit_code = 0 } } | Out-Null
  $zip = Invoke-RecordedStep -Name 'zip' -Results $stepResults -Action { New-CandidateZip }
  Invoke-RecordedStep -Name 'fixture' -Results $stepResults -Action { New-Fixture; @{ exit_code = 0 } } | Out-Null
  Invoke-RecordedStep -Name 'fixture_before_manifest' -Results $stepResults -Action { Write-FileManifest -Root $fixtureRoot -RelativePaths @('db','metadata','output','logs','cache') -OutputPath $fixtureBefore | Out-Null; @{ exit_code = 0 } } | Out-Null
  Invoke-RecordedStep -Name 'refresh_before_manifest' -Results $stepResults -Action { Write-FileManifest -Root $refreshFailureRoot -RelativePaths @('db','metadata','output','logs','cache') -OutputPath $refreshBefore | Out-Null; @{ exit_code = 0 } } | Out-Null
  $childEnv = New-ChildEnvironment -DataRoot $fixtureRoot -LocalAppData (Join-Path $taskRoot 'localappdata-diagnostic')
  Invoke-RecordedStep -Name 'environment_audit' -Results $stepResults -Action { foreach ($name in (Get-ChildItem Env: | Where-Object { $_.Name -match '^(CVM|SQLITE_PATH|DATABASE_URL)' })) { if (-not $childEnv.ContainsKey($name.Name)) { throw "Inherited CVM/path environment variable is not overwritten or documented: $($name.Name)" } }; @{ exit_code = 0 } } | Out-Null
  $diagnostic = Invoke-RecordedStep -Name 'diagnostic' -Results $stepResults -Action { Invoke-IsolatedDiagnostic -ChildEnvironment $childEnv -ExpectedIdentity $expectedIdentity }
  $ui = Invoke-RecordedStep -Name 'packaged_ui' -Results $stepResults -Action { Invoke-PackagedUi -ChildEnvironment $childEnv -ExpectedIdentity $expectedIdentity }
  $refreshFailure = Invoke-RecordedStep -Name 'refresh_failure' -Results $stepResults -Action { Test-RefreshFailureStartup -ExpectedIdentity $expectedIdentity }
  $workbook = Invoke-RecordedStep -Name 'workbook' -Results $stepResults -Action { $value = Test-WorkbookOpen; $value.exit_code = 0; $value }
  $updater = Invoke-RecordedStep -Name 'updater' -Results $stepResults -Action { Invoke-ScratchUpdaterTest }
  $evidence.status = 'pass'
} catch {
  $primaryFailure = $_
  $evidence.status = 'failed'
  $evidence.primary_failure = @{ message = $_.Exception.Message; type = $_.Exception.GetType().FullName }
} finally {
  if (Test-Path -LiteralPath $sourceBefore) {
    try { Invoke-RecordedStep -Name 'source_after_preservation' -Results $stepResults -Action { Write-FileManifest -Root $sourceRoot -RelativePaths $sourcePaths -OutputPath $sourceAfter | Out-Null; Compare-PreservationManifest -BeforePath $sourceBefore -AfterPath $sourceAfter; @{ exit_code = 0 } } | Out-Null } catch { if (-not $primaryFailure) { $primaryFailure = $_; $evidence.status = 'failed'; $evidence.primary_failure = @{ message = $_.Exception.Message } } else { Register-SecondaryFailure -Evidence $evidence -Name 'preservation' -ErrorRecord $_ } }
  }
  if (Test-Path -LiteralPath $fixtureBefore) {
    try {
      Write-FileManifest -Root $fixtureRoot -RelativePaths @('db','metadata','output','logs','cache') -OutputPath $fixtureAfter | Out-Null
      $evidence.fixture_changes = Invoke-RecordedStep -Name 'fixture_classification' -Results $stepResults -Action { @{ exit_code = 0; changes = (Test-FixturePolicy -BeforePath $fixtureBefore -AfterPath $fixtureAfter -Policy 'main') } }
    } catch {
      if (-not $primaryFailure) { $primaryFailure = $_; $evidence.status = 'failed'; $evidence.primary_failure = @{ message = $_.Exception.Message } }
      else { Register-SecondaryFailure -Evidence $evidence -Name 'fixture_classification' -ErrorRecord $_ }
    }
  }
  if (Test-Path -LiteralPath $refreshBefore) {
    try {
      Write-FileManifest -Root $refreshFailureRoot -RelativePaths @('db','metadata','output','logs','cache') -OutputPath $refreshAfter | Out-Null
      $evidence.refresh_failure_fixture_changes = Invoke-RecordedStep -Name 'refresh_failure_classification' -Results $stepResults -Action { @{ exit_code = 0; changes = (Test-FixturePolicy -BeforePath $refreshBefore -AfterPath $refreshAfter -Policy 'refresh-failure') } }
    } catch {
      if (-not $primaryFailure) { $primaryFailure = $_; $evidence.status = 'failed'; $evidence.primary_failure = @{ message = $_.Exception.Message } }
      else { Register-SecondaryFailure -Evidence $evidence -Name 'refresh_failure_classification' -ErrorRecord $_ }
    }
  }
  $evidence.completed_utc = [DateTime]::UtcNow.ToString('o'); $evidence.duration_ms = [int]([DateTime]::UtcNow - $runStarted).TotalMilliseconds
  foreach ($cleanupFailure in $script:CleanupFailures) { if (-not $evidence.secondary_failures) { $evidence.secondary_failures = @() }; $evidence.secondary_failures += $cleanupFailure }
  $evidence.expected_identity = $expectedIdentity; $evidence.canonical_runtime_lock = $runtimeLock; $evidence.zip = $zip; $evidence.diagnostic = $diagnostic; $evidence.ui = $ui; $evidence.refresh_failure = $refreshFailure; $evidence.workbook = $workbook; $evidence.updater = $updater
  try { Invoke-RecordedStep -Name 'summary' -Results $stepResults -Action { Write-EvidenceSummary -Evidence $evidence; @{ exit_code = 0 } } | Out-Null } catch { if (-not $primaryFailure) { $primaryFailure = $_; $evidence.status = 'failed'; $evidence.summary_failure = $_.Exception.Message } else { Register-SecondaryFailure -Evidence $evidence -Name 'summary_failure' -ErrorRecord $_ }; try { $evidence | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $taskRoot 'evidence-summary-fallback.json') -Encoding UTF8 } catch { Register-SecondaryFailure -Evidence $evidence -Name 'summary_fallback' -ErrorRecord $_ } }
}
if ($primaryFailure) { throw $primaryFailure }
