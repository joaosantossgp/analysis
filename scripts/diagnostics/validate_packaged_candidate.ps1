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

function Assert-Descendant {
  param([Parameter(Mandatory)][string]$Parent, [Parameter(Mandatory)][string]$Child)

  $parentPath = [IO.Path]::GetFullPath($Parent).TrimEnd('\', '/')
  $childPath = [IO.Path]::GetFullPath($Child)
  $prefix = $parentPath + [IO.Path]::DirectorySeparatorChar
  if (-not $childPath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Path escapes its approved parent: $childPath (parent: $parentPath)"
  }
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
  param([Parameter(Mandatory)][hashtable]$ChildEnvironment)

  $stdout = Join-Path $taskRoot 'diagnostic.stdout.log'
  $stderr = Join-Path $taskRoot 'diagnostic.stderr.log'
  Assert-Descendant -Parent $taskRoot -Child $stdout
  Assert-Descendant -Parent $taskRoot -Child $stderr
  $p = Start-Process $candidateExe -ArgumentList '--diagnose-runtime','--non-interactive' -Environment $ChildEnvironment -PassThru -Wait -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
  if ($p.ExitCode -ne 0) { throw "Diagnostic failed: $($p.ExitCode)" }
  $diagnosticText = (Get-Content -LiteralPath $stdout -Raw) + (Get-Content -LiteralPath $stderr -Raw)
  $diagnosticLogs = Get-ChildItem -LiteralPath (Join-Path $fixtureRoot 'logs') -File -Recurse -ErrorAction SilentlyContinue | Get-Content -Raw -ErrorAction SilentlyContinue
  $diagnosticText += ($diagnosticLogs -join [Environment]::NewLine)
  foreach ($required in @('frozen', $fixtureRoot, $ChildEnvironment.LOCALAPPDATA)) {
    if ($diagnosticText -notmatch [regex]::Escape($required)) { throw "Diagnostic evidence is missing: $required" }
  }
  $canonicalDocuments = Join-Path $env:USERPROFILE 'Documents\CVMAnalytics'
  if ($diagnosticText -match [regex]::Escape($canonicalDocuments)) { throw 'Diagnostic leaked the canonical Documents root' }
  return [ordered]@{ pid = $p.Id; exit_code = $p.ExitCode; stdout = $stdout; stderr = $stderr }
}

function Invoke-PackagedUi {
  param([Parameter(Mandatory)][hashtable]$ChildEnvironment)

  $uiEnv = $ChildEnvironment.Clone()
  $uiEnv.LOCALAPPDATA = Join-Path $taskRoot 'localappdata-ui'
  $uiEnv.WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$CdpPort --remote-allow-origins=* --proxy-server=http://127.0.0.1:9 --proxy-bypass-list=127.0.0.1;localhost"
  $processStartMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
  $p = Start-Process $candidateExe -Environment $uiEnv -PassThru -WindowStyle Hidden
  try {
    $deadline = (Get-Date).AddSeconds(60)
    do {
      try { $cdp = Invoke-RestMethod "http://127.0.0.1:$CdpPort/json/version"; break }
      catch { Start-Sleep -Milliseconds 250 }
    } while ((Get-Date) -lt $deadline -and -not $p.HasExited)
    if (-not $cdp) { throw 'CDP readiness timeout' }
    $outputDir = Join-Path $taskRoot 'ui'
    Assert-Descendant -Parent $taskRoot -Child $outputDir
    & node (Join-Path $repoRoot 'scripts\diagnostics\validate_packaged_ui.cjs') --cdp-url "http://127.0.0.1:$CdpPort" --output-dir $outputDir --cd-cvm $CdCvm --process-start-ms $processStartMs
    if ($LASTEXITCODE -ne 0) { throw "CDP harness failed: $LASTEXITCODE" }
    if (-not (Test-Path -LiteralPath $uiResultsPath)) { throw "Missing UI results: $uiResultsPath" }
    return [ordered]@{ pid = $p.Id; results = $uiResultsPath }
  } finally {
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
  }
}

function Test-RefreshFailureStartup {
  Assert-Descendant -Parent $taskRoot -Child $refreshFailureRoot
  $failureEnv = New-ChildEnvironment -DataRoot $refreshFailureRoot -LocalAppData (Join-Path $taskRoot 'localappdata-refresh-failure')
  $p = Start-Process $candidateExe -Environment $failureEnv -PassThru -WindowStyle Hidden
  try {
    Start-Sleep -Seconds 13
    if ($p.HasExited) { throw "Refresh-failure candidate exited early: $($p.ExitCode)" }
    $state = & python -c "import sqlite3,sys,json; c=sqlite3.connect(sys.argv[1]); row=c.execute('select cnpj from companies where cd_cvm=?',(int(sys.argv[2]),)).fetchone(); print(json.dumps({'cnpj':None if row is None else row[0]})); c.close()" (Join-Path $refreshFailureRoot 'db\cvm_financials.db') $CdCvm
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect refresh-failure fixture' }
    if ((($state | ConvertFrom-Json).cnpj) -ne $null) { throw 'Offline refresh failure unexpectedly restored the fixture CNPJ' }
    return [ordered]@{ pid = $p.Id; stayed_alive_after_seconds = 13 }
  } finally {
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
  }
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
  try { $excel = New-Object -ComObject Excel.Application } catch [Runtime.InteropServices.COMException] { $comNeedsValidation = $_.Exception.Message }
  if ($excel) {
    try { $excel.DisplayAlerts = $false; $book = $excel.Workbooks.Open($excelPath, 0, $true); $book.Close($false) }
    finally {
      if ($book) { [Runtime.InteropServices.Marshal]::FinalReleaseComObject($book) | Out-Null }
      $excel.Quit()
      [Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel) | Out-Null
    }
  }
  return [ordered]@{ path = $excelPath; sha256 = (Get-FileHash $excelPath -Algorithm SHA256).Hash; openpyxl = $openPyxl; com_needs_validation = $comNeedsValidation }
}

function Invoke-ScratchUpdaterTest {
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
  if (-not (Get-ChildItem -LiteralPath $rollbackRoot -Directory -ErrorAction SilentlyContinue | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'CVMAnalytics.exe') })) { throw 'Updater rollback is missing the old executable' }
  $helperLog = Join-Path $updaterLocalAppData 'CVMAnalytics\update_error.log'
  if (-not (Test-Path -LiteralPath $helperLog) -or (Get-Content -LiteralPath $helperLog -Raw) -notmatch 'relaunch issued OK') { throw 'Updater helper did not record a successful relaunch' }
  foreach ($name in $protected) { if ($before[$name] -ne (Get-FileHash (Join-Path $current "$name\sentinel.txt") -Algorithm SHA256).Hash) { throw "Updater changed protected directory: $name" } }
  return [ordered]@{ pid = $p.Id; protected_directories = $protected }
}

function Compare-PreservationManifest {
  param([Parameter(Mandatory)][string]$BeforePath, [Parameter(Mandatory)][string]$AfterPath)
  if (Compare-Object (Get-Content -LiteralPath $BeforePath) (Get-Content -LiteralPath $AfterPath)) { throw 'Canonical source preservation manifest changed' }
}

function New-Fixture {
  if (Get-Process -Name CVMAnalytics -ErrorAction SilentlyContinue) { throw 'A CVMAnalytics process owns the canonical data root; validation will not contend with it.' }
  Assert-Descendant -Parent $taskRoot -Child $fixtureRoot
  New-Item -ItemType Directory -Force -Path $fixtureRoot | Out-Null
  Backup-SqliteDatabase -Source (Join-Path $sourceRoot 'db\cvm_financials.db') -Destination (Join-Path $fixtureRoot 'db\cvm_financials.db')
  Backup-SqliteDatabase -Source (Join-Path $sourceRoot 'db\energy_kpis.db') -Destination (Join-Path $fixtureRoot 'db\energy_kpis.db')
  $marketCap = Join-Path $sourceRoot 'metadata\b3_market_cap_universe_snapshot.csv'
  if (Test-Path -LiteralPath $marketCap) { New-Item -ItemType Directory -Force -Path (Join-Path $fixtureRoot 'metadata') | Out-Null; Copy-Item -LiteralPath $marketCap -Destination (Join-Path $fixtureRoot 'metadata\b3_market_cap_universe_snapshot.csv') }
  $companyCount = & python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('select count(*) from companies where cd_cvm=?',(int(sys.argv[2]),)).fetchone()[0]); c.close()" (Join-Path $fixtureRoot 'db\cvm_financials.db') $CdCvm
  if ([int]$companyCount -ne 1) { throw "Representative company is missing from fixture: $CdCvm" }
  Copy-Item -LiteralPath $fixtureRoot -Destination $refreshFailureRoot -Recurse -Force
  & python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('update companies set cnpj=NULL where cd_cvm=?',(int(sys.argv[2]),)); c.execute(\"delete from metadata_refresh_state where key like '%success%'\"); c.commit(); c.close()" (Join-Path $refreshFailureRoot 'db\cvm_financials.db') $CdCvm
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
$zip = New-CandidateZip
$sourcePaths = @('input','raw','source_snapshots','db\cvm_financials.db','db\energy_kpis.db')
$sourceBefore = Join-Path $taskRoot 'source-before-manifest.json'
$sourceAfter = Join-Path $taskRoot 'source-after-manifest.json'
$fixtureBefore = Join-Path $taskRoot 'fixture-before-manifest.json'
$fixtureAfter = Join-Path $taskRoot 'fixture-after-manifest.json'
Write-FileManifest -Root $sourceRoot -RelativePaths $sourcePaths -OutputPath $sourceBefore | Out-Null
New-Fixture
Write-FileManifest -Root $fixtureRoot -RelativePaths @('db','metadata','output','logs') -OutputPath $fixtureBefore | Out-Null
$childEnv = New-ChildEnvironment -DataRoot $fixtureRoot -LocalAppData (Join-Path $taskRoot 'localappdata-diagnostic')
foreach ($name in (Get-ChildItem Env: | Where-Object { $_.Name -match '^(CVM|SQLITE_PATH|DATABASE_URL)' })) {
  if ($name.Name -match '(_DIR|_PATH|DATABASE_URL)$' -and -not $childEnv.ContainsKey($name.Name)) { throw "Inherited path-bearing environment variable is not overwritten: $($name.Name)" }
}
$diagnostic = Invoke-IsolatedDiagnostic -ChildEnvironment $childEnv
$ui = Invoke-PackagedUi -ChildEnvironment $childEnv
$refreshFailure = Test-RefreshFailureStartup
$workbook = Test-WorkbookOpen
$updater = Invoke-ScratchUpdaterTest
Write-FileManifest -Root $fixtureRoot -RelativePaths @('db','metadata','output','logs') -OutputPath $fixtureAfter | Out-Null
Write-FileManifest -Root $sourceRoot -RelativePaths $sourcePaths -OutputPath $sourceAfter | Out-Null
Compare-PreservationManifest -BeforePath $sourceBefore -AfterPath $sourceAfter
[ordered]@{
  harness_commit_sha = (git rev-parse HEAD).Trim()
  harness_sha256 = [ordered]@{ controller = (Get-FileHash $PSCommandPath -Algorithm SHA256).Hash; ui = (Get-FileHash (Join-Path $repoRoot 'scripts\diagnostics\validate_packaged_ui.cjs') -Algorithm SHA256).Hash }
  arguments = $PSBoundParameters
  environment_allowlist = $childEnv.Keys | Sort-Object
  completed_utc = [DateTime]::UtcNow.ToString('o')
  zip = $zip
  diagnostic = $diagnostic
  ui = $ui
  refresh_failure = $refreshFailure
  workbook = $workbook
  updater = $updater
  artifacts = @($sourceBefore,$sourceAfter,$fixtureBefore,$fixtureAfter,$uiResultsPath)
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskRoot 'evidence-summary.json') -Encoding UTF8
