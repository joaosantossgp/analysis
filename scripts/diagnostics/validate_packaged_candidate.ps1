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
    foreach ($file in Get-ChildItem -LiteralPath $fullPath -File -Recurse | Sort-Object FullName) {
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
  Assert-Descendant -Parent $taskRoot -Child $stdout
  Assert-Descendant -Parent $taskRoot -Child $stderr
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
  & node (Join-Path $repoRoot 'scripts\diagnostics\validate_packaged_ui.cjs') @arguments
  if ($LASTEXITCODE -ne 0) { throw "CDP harness failed: $LASTEXITCODE" }
}

function Invoke-PackagedUi {
  param([Parameter(Mandatory)][hashtable]$ChildEnvironment, [Parameter(Mandatory)][hashtable]$ExpectedIdentity)

  $uiEnv = $ChildEnvironment.Clone()
  $started = [DateTime]::UtcNow
  $uiEnv.LOCALAPPDATA = Join-Path $taskRoot 'localappdata-ui'
  $uiEnv.WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$CdpPort --remote-allow-origins=* --proxy-server=http://127.0.0.1:9 --proxy-bypass-list=127.0.0.1;localhost"
  $processStartMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
  $p = Start-Process $candidateExe -Environment $uiEnv -PassThru -WindowStyle Hidden
  try {
    $outputDir = Join-Path $taskRoot 'ui'
    Wait-ForCdpBridge -Process $p -OutputDir $outputDir -ProcessStartMs $processStartMs -ExpectedIdentity $ExpectedIdentity
    if (-not (Test-Path -LiteralPath $uiResultsPath)) { throw "Missing UI results: $uiResultsPath" }
    $result = [ordered]@{ status = 'pass'; pid = $p.Id; results = $uiResultsPath; started_utc = $started.ToString('o'); duration_ms = 0 }
  } finally {
    $cleanup = Stop-TrackedProcess -Process $p -Label 'Packaged UI'
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
  $processStartMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
  $p = Start-Process $candidateExe -Environment $failureEnv -PassThru -WindowStyle Hidden
  try {
    Wait-ForCdpBridge -Process $p -OutputDir (Join-Path $taskRoot 'refresh-failure-ui') -ProcessStartMs $processStartMs -ExpectedIdentity $ExpectedIdentity -ReadinessOnly
    Start-Sleep -Seconds 13
    if ($p.HasExited) { throw "Refresh-failure candidate exited early: $($p.ExitCode)" }
    $state = & python -c "import sqlite3,sys,json; c=sqlite3.connect(sys.argv[1]); row=c.execute('select cnpj from companies where cd_cvm=?',(int(sys.argv[2]),)).fetchone(); refresh=c.execute(\"select value from app_settings where key='metadata_last_successful_refresh'\").fetchone(); print(json.dumps({'cnpj':None if row is None else row[0],'metadata_last_successful_refresh':None if refresh is None else refresh[0]})); c.close()" (Join-Path $refreshFailureRoot 'db\cvm_financials.db') $CdCvm
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect refresh-failure fixture' }
    if ((($state | ConvertFrom-Json).cnpj) -ne $null) { throw 'Offline refresh failure unexpectedly restored the fixture CNPJ' }
    if ((($state | ConvertFrom-Json).metadata_last_successful_refresh) -ne $null) { throw 'Offline refresh failure unexpectedly persisted metadata_last_successful_refresh' }
    $result = [ordered]@{ status = 'pass'; pid = $p.Id; stayed_alive_after_seconds = 13; state = ($state | ConvertFrom-Json); started_utc = $started.ToString('o'); duration_ms = 0 }
  } finally {
    $cleanup = Stop-TrackedProcess -Process $p -Label 'Refresh-failure packaged UI'
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
  try { $excel = New-Object -ComObject Excel.Application } catch [Runtime.InteropServices.COMException] { $comNeedsValidation = $_.Exception.Message }
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
  foreach ($path in @($staged, $current, $updaterLocalAppData)) { Assert-Descendant -Parent $taskRoot -Child $path }
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
  $protected = @('data','output','logs','cache','tmp','backup','versions','update_rollback')
  foreach ($name in $protected) { New-Item -ItemType Directory -Force -Path (Join-Path $current $name) | Out-Null; Set-Content -LiteralPath (Join-Path $current "$name\sentinel.txt") -Value $name }
  $before = @{}; foreach ($name in $protected) { $before[$name] = (Get-FileHash (Join-Path $current "$name\sentinel.txt") -Algorithm SHA256).Hash }
  $helper = (Resolve-Path (Join-Path $repoRoot 'desktop\update_helper.ps1')).Path
  $helperEnv = @{ LOCALAPPDATA = $updaterLocalAppData }
  $p = Start-Process powershell.exe -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$helper,'-New',$staged,'-Current',$current) -Environment $helperEnv -PassThru -Wait -WindowStyle Hidden
  if ($p.ExitCode -ne 0) { throw "Updater helper failed: $($p.ExitCode)" }
  if (-not (Test-Path -LiteralPath (Join-Path $current 'relaunch.marker'))) { throw 'Updater did not relaunch the staged executable' }
  if ((Get-Content -LiteralPath (Join-Path $current '_internal\version.txt') -Raw).Trim() -ne 'staged') { throw 'Updater did not copy staged _internal files' }
  $rollbackRoot = Join-Path $updaterLocalAppData 'CVMAnalytics\update_rollback'
  Assert-Descendant -Parent $taskRoot -Child $rollbackRoot
  $rollback = Get-ChildItem -LiteralPath $rollbackRoot -Directory -ErrorAction SilentlyContinue | Where-Object { (Test-Path -LiteralPath (Join-Path $_.FullName 'CVMAnalytics.exe')) -and (Test-Path -LiteralPath (Join-Path $_.FullName '_internal\version.txt')) } | Select-Object -First 1
  if (-not $rollback) { throw 'Updater rollback is missing the old executable or rollback _internal tree' }
  if ((Get-Content -LiteralPath (Join-Path $rollback.FullName '_internal\version.txt') -Raw).Trim() -ne 'old') { throw 'Updater rollback _internal did not preserve the old version' }
  $helperLog = Join-Path $updaterLocalAppData 'CVMAnalytics\update_error.log'
  if (-not (Test-Path -LiteralPath $helperLog) -or (Get-Content -LiteralPath $helperLog -Raw) -notmatch 'relaunch issued OK') { throw 'Updater helper did not record a successful relaunch' }
  foreach ($name in $protected) { if ($before[$name] -ne (Get-FileHash (Join-Path $current "$name\sentinel.txt") -Algorithm SHA256).Hash) { throw "Updater changed protected directory: $name" } }
  return [ordered]@{ status = 'pass'; started_utc = $started.ToString('o'); duration_ms = [int]([DateTime]::UtcNow - $started).TotalMilliseconds; pid = $p.Id; exit_code = $p.ExitCode; protected_directories = $protected; rollback_path = $rollback.FullName }
}

function Compare-PreservationManifest {
  param([Parameter(Mandatory)][string]$BeforePath, [Parameter(Mandatory)][string]$AfterPath)
  $beforeBytes = [IO.File]::ReadAllBytes($BeforePath)
  $afterBytes = [IO.File]::ReadAllBytes($AfterPath)
  if ($beforeBytes.Length -ne $afterBytes.Length -or [Convert]::ToBase64String($beforeBytes) -ne [Convert]::ToBase64String($afterBytes)) { throw 'Canonical source preservation manifest bytes changed' }
}

function Classify-FixtureManifestChanges {
  param([Parameter(Mandatory)][string]$BeforePath, [Parameter(Mandatory)][string]$AfterPath)
  $before = Get-Content -LiteralPath $BeforePath -Raw | ConvertFrom-Json
  $after = Get-Content -LiteralPath $AfterPath -Raw | ConvertFrom-Json
  $beforeByPath = @{}; foreach ($row in @($before)) { $beforeByPath[$row.path] = $row }
  $changes = @()
  foreach ($row in @($after)) {
    $prior = $beforeByPath[$row.path]
    if (-not $prior -or $prior.sha256 -ne $row.sha256 -or $prior.length -ne $row.length) {
      $classification = if ($row.path -like 'db/*' -or $row.path -like 'output/*' -or $row.path -like 'logs/*') { 'expected_fixture_runtime_change' } else { 'unexpected_fixture_change' }
      $changes += [ordered]@{ path = $row.path; classification = $classification; before = $prior; after = $row }
    }
  }
  if ($changes | Where-Object { $_.classification -eq 'unexpected_fixture_change' }) { throw 'Fixture changed outside expected database/output/log paths' }
  return $changes
}

function New-Fixture {
  Assert-Descendant -Parent $taskRoot -Child $fixtureRoot
  New-Item -ItemType Directory -Force -Path $fixtureRoot | Out-Null
  Backup-SqliteDatabase -Source (Join-Path $sourceRoot 'db\cvm_financials.db') -Destination (Join-Path $fixtureRoot 'db\cvm_financials.db')
  Backup-SqliteDatabase -Source (Join-Path $sourceRoot 'db\energy_kpis.db') -Destination (Join-Path $fixtureRoot 'db\energy_kpis.db')
  $marketCap = Join-Path $sourceRoot 'metadata\b3_market_cap_universe_snapshot.csv'
  if (Test-Path -LiteralPath $marketCap) { New-Item -ItemType Directory -Force -Path (Join-Path $fixtureRoot 'metadata') | Out-Null; Copy-Item -LiteralPath $marketCap -Destination (Join-Path $fixtureRoot 'metadata\b3_market_cap_universe_snapshot.csv') }
  $companyCount = & python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('select count(*) from companies where cd_cvm=?',(int(sys.argv[2]),)).fetchone()[0]); c.close()" (Join-Path $fixtureRoot 'db\cvm_financials.db') $CdCvm
  if ([int]$companyCount -ne 1) { throw "Representative company is missing from fixture: $CdCvm" }
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
$runStarted = [DateTime]::UtcNow
$stepResults = @()
$expectedIdentity = Get-ExpectedCandidateIdentity
$runtimeLock = Inspect-CanonicalRuntimeLock
$sourcePaths = @('input','raw','source_snapshots','db\cvm_financials.db','db\energy_kpis.db')
$sourceBefore = Join-Path $taskRoot 'source-before-manifest.json'
$sourceAfter = Join-Path $taskRoot 'source-after-manifest.json'
$fixtureBefore = Join-Path $taskRoot 'fixture-before-manifest.json'
$fixtureAfter = Join-Path $taskRoot 'fixture-after-manifest.json'
Write-FileManifest -Root $sourceRoot -RelativePaths $sourcePaths -OutputPath $sourceBefore | Out-Null
$stepResults += [ordered]@{ name = 'source_before_manifest'; started_utc = $runStarted.ToString('o'); duration_ms = 0; status = 'pass'; pid = $null; exit_code = 0 }
$zip = New-CandidateZip
New-Fixture
Write-FileManifest -Root $fixtureRoot -RelativePaths @('db','metadata','output','logs') -OutputPath $fixtureBefore | Out-Null
$childEnv = New-ChildEnvironment -DataRoot $fixtureRoot -LocalAppData (Join-Path $taskRoot 'localappdata-diagnostic')
foreach ($name in (Get-ChildItem Env: | Where-Object { $_.Name -match '^(CVM|SQLITE_PATH|DATABASE_URL)' })) {
  if ($name.Name -match '(_DIR|_PATH|DATABASE_URL)$' -and -not $childEnv.ContainsKey($name.Name)) { throw "Inherited path-bearing environment variable is not overwritten: $($name.Name)" }
}
$diagnostic = Invoke-IsolatedDiagnostic -ChildEnvironment $childEnv -ExpectedIdentity $expectedIdentity
$ui = Invoke-PackagedUi -ChildEnvironment $childEnv -ExpectedIdentity $expectedIdentity
$refreshFailure = Test-RefreshFailureStartup -ExpectedIdentity $expectedIdentity
$workbook = Test-WorkbookOpen
$updater = Invoke-ScratchUpdaterTest
Write-FileManifest -Root $fixtureRoot -RelativePaths @('db','metadata','output','logs') -OutputPath $fixtureAfter | Out-Null
$fixtureChanges = Classify-FixtureManifestChanges -BeforePath $fixtureBefore -AfterPath $fixtureAfter
Write-FileManifest -Root $sourceRoot -RelativePaths $sourcePaths -OutputPath $sourceAfter | Out-Null
Compare-PreservationManifest -BeforePath $sourceBefore -AfterPath $sourceAfter
$stepResults += @(
  [ordered]@{ name = 'runtime_lock'; status = 'pass'; started_utc = $runtimeLock.checked_utc; duration_ms = 0; pid = $runtimeLock.owner.pid; exit_code = $null },
  [ordered]@{ name = 'diagnostic'; status = $diagnostic.status; started_utc = $diagnostic.started_utc; duration_ms = $diagnostic.duration_ms; pid = $diagnostic.pid; exit_code = $diagnostic.exit_code },
  [ordered]@{ name = 'packaged_ui'; status = $ui.status; started_utc = $ui.started_utc; duration_ms = $ui.duration_ms; pid = $ui.pid; exit_code = $ui.cleanup.exit_code },
  [ordered]@{ name = 'refresh_failure'; status = $refreshFailure.status; started_utc = $refreshFailure.started_utc; duration_ms = $refreshFailure.duration_ms; pid = $refreshFailure.pid; exit_code = $refreshFailure.cleanup.exit_code },
  [ordered]@{ name = 'updater'; status = $updater.status; started_utc = $updater.started_utc; duration_ms = $updater.duration_ms; pid = $updater.pid; exit_code = $updater.exit_code },
  [ordered]@{ name = 'preservation'; status = 'pass'; started_utc = [DateTime]::UtcNow.ToString('o'); duration_ms = 0; pid = $null; exit_code = 0 }
)
$artifactInventory = @()
foreach ($artifact in Get-ChildItem -LiteralPath $taskRoot -File -Recurse | Sort-Object FullName) {
  Assert-Descendant -Parent $taskRoot -Child $artifact.FullName
  $artifactInventory += [ordered]@{ path = $artifact.FullName; bytes = $artifact.Length; sha256 = (Get-FileHash -LiteralPath $artifact.FullName -Algorithm SHA256).Hash }
}
[ordered]@{
  harness_commit_sha = (git rev-parse HEAD).Trim()
  harness_sha256 = [ordered]@{ controller = (Get-FileHash $PSCommandPath -Algorithm SHA256).Hash; ui = (Get-FileHash (Join-Path $repoRoot 'scripts\diagnostics\validate_packaged_ui.cjs') -Algorithm SHA256).Hash }
  arguments = $PSBoundParameters
  environment_allowlist = $childEnv.Keys | Sort-Object
  started_utc = $runStarted.ToString('o')
  completed_utc = [DateTime]::UtcNow.ToString('o')
  duration_ms = [int]([DateTime]::UtcNow - $runStarted).TotalMilliseconds
  expected_identity = $expectedIdentity
  canonical_runtime_lock = $runtimeLock
  step_results = $stepResults
  zip = $zip
  diagnostic = $diagnostic
  ui = $ui
  refresh_failure = $refreshFailure
  workbook = $workbook
  updater = $updater
  fixture_changes = $fixtureChanges
  artifact_inventory = $artifactInventory
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskRoot 'evidence-summary.json') -Encoding UTF8
