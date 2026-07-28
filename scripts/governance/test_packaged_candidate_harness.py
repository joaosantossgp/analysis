from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTROLLER = ROOT / "scripts/diagnostics/validate_packaged_candidate.ps1"
UI_HARNESS = ROOT / "scripts/diagnostics/validate_packaged_ui.cjs"


def _run_powershell_probe(tmp_path: Path, functions: tuple[str, ...], body: str) -> subprocess.CompletedProcess[str]:
    function_names = ", ".join(f"'{name}'" for name in functions)
    controller_path = CONTROLLER.as_posix().replace("'", "''")
    probe = tmp_path / "harness-behavior-probe.ps1"
    probe.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            $tokens = $null
            $parseErrors = $null
            $ast = [System.Management.Automation.Language.Parser]::ParseFile(
              '{controller_path}',
              [ref]$tokens,
              [ref]$parseErrors
            )
            if ($parseErrors.Count -ne 0) {{ throw ($parseErrors | Out-String) }}
            foreach ($functionName in @({function_names})) {{
              $definition = $ast.FindAll({{
                param($node)
                $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
                  $node.Name -eq $functionName
              }}, $true) | Select-Object -First 1
              if (-not $definition) {{ throw "Missing committed function: $functionName" }}
              . ([scriptblock]::Create($definition.Extent.Text))
            }}
            {body}
            """
        ),
        encoding="utf-8",
    )
    return subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(probe)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_packaged_candidate_harness_is_committed_and_fail_closed() -> None:
    missing = [str(path.relative_to(ROOT)) for path in (CONTROLLER, UI_HARNESS) if not path.is_file()]
    assert not missing, f"missing committed packaged-candidate harness paths: {', '.join(missing)}"

    controller = CONTROLLER.read_text(encoding="utf-8")
    ui_harness = UI_HARNESS.read_text(encoding="utf-8")

    for parameter in ("Mode", "CandidateDir", "EvidenceDir", "SourceDataRoot", "CdCvm", "CdpPort"):
        assert re.search(rf"\${parameter}\b", controller), f"missing PowerShell parameter: {parameter}"
    for mode in ("ValidateInputs", "Run"):
        assert mode in controller

    for token in (
        "Assert-Descendant",
        "$taskRoot",
        "$candidateDir",
        "$fixtureRoot",
        "$staged",
        "$current",
        "$updaterLocalAppData",
        "$uiResultsPath",
        "Write-FileManifest",
        "Backup-SqliteDatabase",
        "Invoke-IsolatedDiagnostic",
        "Invoke-PackagedUi",
        "Test-WorkbookOpen",
        "Invoke-ScratchUpdaterTest",
        "Compare-PreservationManifest",
        "a.backup(b)",
        "before-manifest",
        "after-manifest",
        "-New",
        "-Current",
        "data",
        "output",
        "logs",
        "cache",
        "tmp",
        "backup",
        "versions",
        "update_rollback",
        "$childEnv",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "try",
        "finally",
        "Stop-TrackedProcess -Process $p",
    ):
        assert token in controller, f"controller contract missing: {token}"

    assert not re.search(r"\$env:(?:CVM\w*|LOCALAPPDATA|DATABASE_URL)\s*=", controller)

    for token in (
        "connectOverCDP",
        "get_app_status",
        "get_companies",
        "get_company_info",
        "get_company_financial_readiness",
        "get_sin_kpi_dashboard",
        "export_company_excel",
        "#/empresas",
        "#/empresas/",
        "#/indicators?section=energy&sub=sin",
        "#/settings/diagnostics",
        "1366",
        "768",
        "1920",
        "1080",
        "Buffer.byteLength",
        "console",
        "network",
            "process.exitCode = 1",
    ):
        assert token in ui_harness, f"UI harness contract missing: {token}"


def test_refresh_failure_uses_the_real_setting_and_repeats_bridge_readiness() -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")
    assert "metadata_refresh_state" not in controller
    assert "app_settings" in controller
    assert "metadata_last_successful_refresh" in controller
    assert "function Wait-ForCdpBridge" in controller
    assert "-ReadinessOnly" in controller
    assert "refresh_failure_sql.json" in controller


def test_controller_inspects_the_runtime_lock_before_source_hashing_and_checks_identity() -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")
    assert "function Inspect-CanonicalRuntimeLock" in controller
    assert controller.index("Inspect-CanonicalRuntimeLock") < controller.index("Write-FileManifest -Root $sourceRoot")
    assert "function Get-ExpectedCandidateIdentity" in controller
    assert "build_commit" in controller
    ui_harness = UI_HARNESS.read_text(encoding="utf-8")
    assert "candidate version mismatch" in ui_harness
    assert "candidate build SHA mismatch" in ui_harness


def test_controller_rejects_reparse_escapes_and_compares_preservation_bytes() -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")
    assert "function Resolve-ApprovedPath" in controller
    assert "ReparsePoint" in controller
    assert "[IO.File]::ReadAllBytes" in controller
    compare_body = controller.split("function Compare-PreservationManifest", 1)[1].split("function ", 1)[0]
    assert "Compare-Object" not in compare_body
    assert "function Classify-FixtureManifestChanges" in controller


def test_evidence_and_cleanup_contract_is_structured_and_fail_closed() -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")
    ui_harness = UI_HARNESS.read_text(encoding="utf-8")
    for token in (
        "function Stop-TrackedProcess",
        "Wait-Process -Id $Process.Id",
        "artifact_inventory",
        "step_results",
        "started_utc",
        "duration_ms",
        "read_only_open_succeeded",
        "no_repair_prompt_observable",
        "com_activation",
        "formula_count",
        "file_size_bytes",
        "rollback _internal",
    ):
        assert token in controller
    assert "writeFailureArtifacts" in ui_harness
    assert "finally" in ui_harness
    assert "process.exitCode = 1" in ui_harness


def test_failure_finalization_and_mutation_targets_are_fail_closed() -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")
    ui_harness = UI_HARNESS.read_text(encoding="utf-8")
    for token in (
        "function Assert-MutationTargets",
        "function Write-EvidenceSummary",
        "function Invoke-RecordedStep",
        "Get-Process -Name CVMAnalytics",
        "source-after-manifest.json",
        "primary_failure",
        "finally {",
        "CVMAnalytics\\update_rollback",
        "CVM_ENERGY_HOURLY_HOT_COLD_MANIFEST",
        "refresh-failure-before-manifest.json",
        "refresh-failure-after-manifest.json",
        "before-only",
        "unexpected_fixture_database_change",
        "old_executable_sha256",
        "rollback_executable_sha256",
    ):
        assert token in controller
    assert "results.status = \"failed\"" in ui_harness
    assert "results.error" in ui_harness


def test_finalization_binds_classifier_failures_and_exact_targets() -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")
    assert "function Register-SecondaryFailure" in controller
    assert "function Test-FixturePolicy" in controller
    assert "exists':r is not None" in controller
    assert "Representative company row disappeared" in controller
    assert "summary_failure" in controller
    assert "evidence-summary.json" in controller
    assert "Assert-NoReparseTree" in controller
    assert "refresh_failure_sql.json" in controller
    assert "0x80040154" in controller
    finalization = controller.split("} finally {", 1)[-1]
    assert "primary_failure" in finalization
    assert "Finalize-EvidenceSummary -Evidence $evidence -StepResults $stepResults" in finalization


def test_extracted_reparse_guard_accepts_task_root_equality(tmp_path: Path) -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")

    def function_source(name: str, next_name: str) -> str:
        return controller.split(f"function {name}", 1)[1].split(f"function {next_name}", 1)[0]

    script = "\n".join(
        [
            "function Resolve-ApprovedPath" + function_source("Resolve-ApprovedPath", "Assert-Descendant"),
            "function Assert-Descendant" + function_source("Assert-Descendant", "Stop-TrackedProcess"),
            "function Assert-NoReparseTree" + function_source("Assert-NoReparseTree", "Prepare-RunAttempt"),
            f"$taskRoot = '{tmp_path.as_posix()}'",
            "New-Item -ItemType Directory -Force -Path $taskRoot | Out-Null",
            "Assert-NoReparseTree -Root $taskRoot",
        ]
    )
    probe = tmp_path / "root-equality-probe.ps1"
    probe.write_text(script, encoding="utf-8")
    result = subprocess.run(["pwsh", "-NoProfile", "-File", str(probe)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_recorded_step_accepts_an_empty_array_list(tmp_path: Path) -> None:
    result = _run_powershell_probe(
        tmp_path,
        ("Invoke-RecordedStep",),
        """
        $results = [System.Collections.ArrayList]@()
        $value = Invoke-RecordedStep -Name 'first' -Results $results -Action {
          [ordered]@{ exit_code = 0; marker = 'executed' }
        }
        if ($value.marker -ne 'executed') { throw 'The recorded action did not execute' }
        if ($results.Count -ne 1 -or $results[0].name -ne 'first' -or $results[0].status -ne 'pass') {
          throw 'The first recorded step was not appended to the empty ArrayList'
        }
        try {
          Invoke-RecordedStep -Name 'generic-failure' -Results $results -Action {
            $failure = [System.Exception]::new('generic child failure')
            $failure.Data['pid'] = 4321
            $failure.Data['exit_code'] = 17
            $failure.Data['stdout'] = 'child.stdout.log'
            $failure.Data['stderr'] = 'child.stderr.log'
            $failure.Data['details'] = @{ stage = 'post-probe' }
            throw $failure
          } | Out-Null
        } catch {}
        $failed = $results[1]
        if ($failed.status -ne 'failed' -or $failed.pid -ne 4321 -or $failed.exit_code -ne 17) {
          throw 'Invoke-RecordedStep did not consume generic exception process data'
        }
        if ($failed.stdout -ne 'child.stdout.log' -or $failed.stderr -ne 'child.stderr.log' -or $failed.details.stage -ne 'post-probe') {
          throw 'Invoke-RecordedStep lost generic exception artifacts or details'
        }
        """,
    )
    assert result.returncode == 0, result.stderr


def test_prepare_run_attempt_archives_known_outputs_and_starts_with_fresh_fixtures(tmp_path: Path) -> None:
    task_root = (tmp_path / "evidence").as_posix().replace("'", "''")
    result = _run_powershell_probe(
        tmp_path,
        (
            "Resolve-ApprovedPath",
            "Assert-Descendant",
            "Assert-MutationTargets",
            "Assert-NoReparseTree",
            "Prepare-RunAttempt",
        ),
        f"""
        $taskRoot = '{task_root}'
        $fixtureRoot = Join-Path $taskRoot 'fixture'
        $refreshFailureRoot = Join-Path $taskRoot 'fixture-refresh-failure'
        New-Item -ItemType Directory -Force -Path $fixtureRoot,$refreshFailureRoot | Out-Null
        Set-Content -LiteralPath (Join-Path $fixtureRoot 'stale.txt') -Value 'main'
        Set-Content -LiteralPath (Join-Path $refreshFailureRoot 'stale.txt') -Value 'refresh'
        Set-Content -LiteralPath (Join-Path $taskRoot 'canonical-runtime-lock.json') -Value '{{}}'
        Set-Content -LiteralPath (Join-Path $taskRoot 'preflight.keep') -Value 'keep'

        Prepare-RunAttempt

        if (Test-Path -LiteralPath $fixtureRoot) {{ throw 'Main fixture was not removed from the active attempt' }}
        if (Test-Path -LiteralPath $refreshFailureRoot) {{ throw 'Refresh fixture was not removed from the active attempt' }}
        if (-not (Test-Path -LiteralPath (Join-Path $taskRoot 'preflight.keep'))) {{ throw 'Unrelated preflight evidence was moved' }}
        $attempt = @(Get-ChildItem -LiteralPath (Join-Path $taskRoot 'attempts') -Directory)
        if ($attempt.Count -ne 1) {{ throw "Expected exactly one attempt archive, found $($attempt.Count)" }}
        foreach ($relative in @('fixture/stale.txt','fixture-refresh-failure/stale.txt','canonical-runtime-lock.json')) {{
          if (-not (Test-Path -LiteralPath (Join-Path $attempt[0].FullName $relative))) {{
            throw "Known stale output was not archived: $relative"
          }}
        }}
        """,
    )
    assert result.returncode == 0, result.stderr


def test_fixture_classifier_enforces_optional_root_and_policy_boundaries(tmp_path: Path) -> None:
    fixture_dir = (tmp_path / "classifier").as_posix().replace("'", "''")
    result = _run_powershell_probe(
        tmp_path,
        ("Classify-FixtureManifestChanges",),
        f"""
        $root = '{fixture_dir}'
        New-Item -ItemType Directory -Force -Path $root | Out-Null
        function Write-ProbeManifest([string]$Name, [object[]]$Rows) {{
          $path = Join-Path $root "$Name.json"
          @($Rows) | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $path -Encoding UTF8
          return $path
        }}
        function Assert-Rejected([string]$Label, [object[]]$Before, [object[]]$After, [string]$Policy) {{
          $beforePath = Write-ProbeManifest "$Label-before" $Before
          $afterPath = Write-ProbeManifest "$Label-after" $After
          $threw = $false
          try {{ Classify-FixtureManifestChanges -BeforePath $beforePath -AfterPath $afterPath -Policy $Policy | Out-Null }}
          catch {{ $threw = $true }}
          if (-not $threw) {{ throw "Classifier accepted forbidden change: $Label" }}
        }}

        foreach ($status in @('missing','empty')) {{
          $beforePath = Write-ProbeManifest "allowed-$status-before" @(@{{ path = 'output'; status = $status }})
          $afterPath = Write-ProbeManifest "allowed-$status-after" @(@{{ path = 'output/report.xlsx'; status = 'present'; length = 1; sha256 = 'a' }})
          $changes = @(Classify-FixtureManifestChanges -BeforePath $beforePath -AfterPath $afterPath -Policy 'main')
          if ($changes.Count -ne 1 -or $changes[0].classification -ne 'expected_fixture_runtime_change') {{
            throw "Main policy rejected optional $status output materialization"
          }}
        }}
        $beforePath = Write-ProbeManifest 'refresh-log-before' @(@{{ path = 'logs'; status = 'missing' }})
        $afterPath = Write-ProbeManifest 'refresh-log-after' @(@{{ path = 'logs/runtime.log'; status = 'present'; length = 1; sha256 = 'b' }})
        Classify-FixtureManifestChanges -BeforePath $beforePath -AfterPath $afterPath -Policy 'refresh-failure' | Out-Null

        foreach ($policy in @('main','refresh-failure')) {{
          foreach ($rootName in @('output','logs','cache')) {{
            $beforePath = Write-ProbeManifest "$policy-$rootName-empty-before" @(@{{ path = $rootName; status = 'missing' }})
            $afterPath = Write-ProbeManifest "$policy-$rootName-empty-after" @(@{{ path = $rootName; status = 'empty' }})
            $changes = @(Classify-FixtureManifestChanges -BeforePath $beforePath -AfterPath $afterPath -Policy $policy)
            if ($changes.Count -ne 1 -or $changes[0].classification -ne 'expected_fixture_runtime_change') {{
              throw "$policy policy rejected exact optional-root missing-to-empty materialization: $rootName"
            }}
          }}
        }}
        Assert-Rejected 'status-transition' @(@{{ path = 'metadata'; status = 'empty' }}) @(@{{ path = 'metadata'; status = 'missing' }}) 'main'
        Assert-Rejected 'metadata-materialization' @(@{{ path = 'metadata'; status = 'missing' }}) @(@{{ path = 'metadata'; status = 'empty' }}) 'main'
        Assert-Rejected 'deletion' @(@{{ path = 'output/report.xlsx'; status = 'present'; length = 1; sha256 = 'a' }}) @() 'main'
        Assert-Rejected 'database-write' @(@{{ path = 'db/app.db'; status = 'present'; length = 1; sha256 = 'a' }}) @(@{{ path = 'db/app.db'; status = 'present'; length = 2; sha256 = 'b' }}) 'main'
        Assert-Rejected 'metadata-write' @(@{{ path = 'metadata/source.csv'; status = 'present'; length = 1; sha256 = 'a' }}) @(@{{ path = 'metadata/source.csv'; status = 'present'; length = 2; sha256 = 'b' }}) 'main'
        Assert-Rejected 'refresh-output' @(@{{ path = 'output'; status = 'missing' }}) @(@{{ path = 'output/report.xlsx'; status = 'present'; length = 1; sha256 = 'a' }}) 'refresh-failure'
        """,
    )
    assert result.returncode == 0, result.stderr


def test_fixture_classifier_allows_only_new_sidecars_for_unchanged_tracked_database(
    tmp_path: Path,
) -> None:
    fixture_dir = (tmp_path / "sidecar-classifier").as_posix().replace("'", "''")
    result = _run_powershell_probe(
        tmp_path,
        ("Classify-FixtureManifestChanges",),
        f"""
        $root = '{fixture_dir}'
        New-Item -ItemType Directory -Force -Path $root | Out-Null
        function Write-ProbeManifest([string]$Name, [object[]]$Rows) {{
          $path = Join-Path $root "$Name.json"
          @($Rows) | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $path -Encoding UTF8
          return $path
        }}
        function Assert-Rejected([string]$Label, [object[]]$Before, [object[]]$After) {{
          $beforePath = Write-ProbeManifest "$Label-before" $Before
          $afterPath = Write-ProbeManifest "$Label-after" $After
          $threw = $false
          try {{ Classify-FixtureManifestChanges -BeforePath $beforePath -AfterPath $afterPath -Policy 'main' | Out-Null }}
          catch {{ $threw = $true }}
          if (-not $threw) {{ throw "Classifier accepted forbidden SQLite sidecar state: $Label" }}
        }}

        $primary = @{{ path = 'db/cvm_financials.db'; status = 'present'; length = 100; sha256 = 'primary-hash' }}
        $wal = @{{ path = 'db/cvm_financials.db-wal'; status = 'present'; length = 20; sha256 = 'wal-hash' }}
        $shm = @{{ path = 'db/cvm_financials.db-shm'; status = 'present'; length = 10; sha256 = 'shm-hash' }}
        $beforePath = Write-ProbeManifest 'allowed-before' @($primary)
        $afterPath = Write-ProbeManifest 'allowed-after' @($primary,$wal,$shm)
        $changes = @(Classify-FixtureManifestChanges -BeforePath $beforePath -AfterPath $afterPath -Policy 'main')
        if ($changes.Count -ne 2) {{ throw "Expected two explicit sidecar changes, found $($changes.Count)" }}
        foreach ($change in $changes) {{
          if ($change.classification -ne 'expected_fixture_runtime_sidecar') {{
            throw "Sidecar lacks explicit runtime classification: $($change.path)"
          }}
          if ($change.sidecar.primary_path -ne 'db/cvm_financials.db' -or
              $change.sidecar.primary_sha256 -ne 'primary-hash' -or
              [int64]$change.sidecar.primary_length -ne 100 -or
              $change.sidecar.kind -notin @('wal','shm')) {{
            throw "Sidecar evidence is incomplete: $($change.path)"
          }}
        }}

        $changedPrimary = @{{ path = 'db/cvm_financials.db'; status = 'present'; length = 101; sha256 = 'changed-primary' }}
        Assert-Rejected 'modified-primary' @($primary) @($changedPrimary,$wal)
        Assert-Rejected 'deleted-primary' @($primary) @($wal)
        Assert-Rejected 'pre-existing-sidecar' @($primary,$wal) @($primary,$wal)
        $changedWal = @{{ path = 'db/cvm_financials.db-wal'; status = 'present'; length = 21; sha256 = 'changed-wal' }}
        Assert-Rejected 'modified-sidecar' @($primary,$wal) @($primary,$changedWal)
        Assert-Rejected 'deleted-sidecar' @($primary,$wal) @($primary)
        $unhashedPrimary = @{{ path = 'db/cvm_financials.db'; status = 'present' }}
        Assert-Rejected 'unhashed-primary' @($unhashedPrimary) @($unhashedPrimary,$wal)
        $arbitrary = @{{ path = 'db/arbitrary.db'; status = 'present'; length = 1; sha256 = 'arbitrary' }}
        Assert-Rejected 'arbitrary-db-addition' @($primary) @($primary,$arbitrary)
        """,
    )
    assert result.returncode == 0, result.stderr


def test_harness_provenance_contains_invocation_environment_and_source_hashes(tmp_path: Path) -> None:
    result = _run_powershell_probe(
        tmp_path,
        ("Get-HarnessProvenance",),
        f"""
        $childEnvironment = @{{
          CVMANALYTICS_DATA_DIR = 'C:/scratch/fixture'
          SQLITE_PATH = 'C:/scratch/fixture/db/app.db'
          LOCALAPPDATA = 'C:/scratch/localappdata'
          HTTP_PROXY = 'http://127.0.0.1:9'
        }}
        $provenance = Get-HarnessProvenance `
          -Mode 'Run' `
          -CandidateDir 'C:/repo/dist/CVMAnalytics' `
          -EvidenceDir 'C:/repo/scratch/task-7' `
          -SourceDataRoot 'C:/Users/operator/Documents/CVMAnalytics' `
          -CdCvm 9512 `
          -CdpPort 9223 `
          -ChildEnvironment $childEnvironment `
          -ControllerPath '{CONTROLLER.as_posix()}' `
          -UiHarnessPath '{UI_HARNESS.as_posix()}'
        foreach ($name in @('Mode','CandidateDir','EvidenceDir','SourceDataRoot','CdCvm','CdpPort')) {{
          if ($null -eq $provenance.invocation_arguments[$name]) {{ throw "Missing invocation argument: $name" }}
        }}
        if (@($provenance.environment_allowlist).Count -ne 4) {{ throw 'Environment allowlist is incomplete' }}
        if ($provenance.child_path_map.HTTP_PROXY) {{ throw 'Proxy URL leaked into the child path map' }}
        foreach ($name in @('CVMANALYTICS_DATA_DIR','SQLITE_PATH','LOCALAPPDATA')) {{
          if (-not $provenance.child_path_map[$name]) {{ throw "Safe child path map is missing: $name" }}
        }}
        if ($provenance.harness_files.controller.sha256 -ne (Get-FileHash -LiteralPath '{CONTROLLER.as_posix()}' -Algorithm SHA256).Hash.ToLowerInvariant()) {{
          throw 'Controller source hash is absent or inaccurate'
        }}
        if ($provenance.harness_files.ui_harness.sha256 -ne (Get-FileHash -LiteralPath '{UI_HARNESS.as_posix()}' -Algorithm SHA256).Hash.ToLowerInvariant()) {{
          throw 'UI harness source hash is absent or inaccurate'
        }}
        """,
    )
    assert result.returncode == 0, result.stderr


def test_frozen_diagnostic_requires_the_exact_true_boolean_line(tmp_path: Path) -> None:
    result = _run_powershell_probe(
        tmp_path,
        ("Test-FrozenDiagnosticEvidence",),
        """
        Test-FrozenDiagnosticEvidence -DiagnosticText "header`nfrozen: True`nfooter"
        Test-FrozenDiagnosticEvidence -DiagnosticText "FROZEN: true"
        foreach ($invalid in @('frozen: False','not frozen','frozen: truthy')) {
          $threw = $false
          try { Test-FrozenDiagnosticEvidence -DiagnosticText $invalid } catch { $threw = $true }
          if (-not $threw) { throw "Accepted invalid frozen evidence: $invalid" }
        }
        """,
    )
    assert result.returncode == 0, result.stderr


def test_cdp_child_launch_creates_validated_redirect_directory_for_real_process(
    tmp_path: Path,
) -> None:
    task_root = (tmp_path / "cdp-output").as_posix().replace("'", "''")
    result = _run_powershell_probe(
        tmp_path,
        (
            "Resolve-ApprovedPath",
            "Assert-Descendant",
            "Assert-MutationTargets",
            "Assert-NoReparseTree",
            "Add-HiddenWindowStyle",
            "Start-CdpHarnessProcess",
        ),
        f"""
        $taskRoot = '{task_root}'
        New-Item -ItemType Directory -Force -Path $taskRoot | Out-Null
        $outputDir = Join-Path $taskRoot 'ui'
        $harnessPath = Join-Path $taskRoot 'redirect-probe.cjs'
        [IO.File]::WriteAllText($harnessPath, "process.stdout.write('redirect-out'); process.stderr.write('redirect-err');")
        if (Test-Path -LiteralPath $outputDir) {{ throw 'Probe output directory unexpectedly pre-exists' }}
        $result = Start-CdpHarnessProcess -OutputDir $outputDir -HarnessPath $harnessPath -Arguments @()
        if ($result.exit_code -ne 0 -or -not $result.pid) {{
          throw 'Real Node child evidence is incomplete'
        }}
        if (-not (Test-Path -LiteralPath $outputDir -PathType Container)) {{ throw 'Redirect parent was not created' }}
        if ([IO.File]::ReadAllText($result.stdout) -cne 'redirect-out') {{ throw 'Real stdout redirect was not captured' }}
        if ([IO.File]::ReadAllText($result.stderr) -cne 'redirect-err') {{ throw 'Real stderr redirect was not captured' }}
        """,
    )
    assert result.returncode == 0, result.stderr
    controller = CONTROLLER.read_text(encoding="utf-8")
    launch_body = controller.split("function Start-CdpHarnessProcess", 1)[1].split(
        "function Wait-ForCdpBridge", 1
    )[0]
    launch = launch_body.index("$node = Start-Process")
    assert launch_body.index("Assert-MutationTargets", 0, launch) < launch
    assert launch_body.index("Assert-NoReparseTree", 0, launch) < launch
    assert launch_body.index("New-Item", 0, launch) < launch
    wait_body = controller.split("function Wait-ForCdpBridge", 1)[1].split(
        "function Invoke-PackagedUi", 1
    )[0]
    assert "Start-CdpHarnessProcess" in wait_body


def test_packaged_diagnostic_evidence_uses_only_bounded_fixture_artifacts(
    tmp_path: Path,
) -> None:
    task_root = (tmp_path / "diagnostic-evidence").as_posix().replace("'", "''")
    result = _run_powershell_probe(
        tmp_path,
        (
            "Resolve-ApprovedPath",
            "Assert-Descendant",
            "Assert-ExistingDescendant",
            "Test-FrozenDiagnosticEvidence",
            "Read-PackagedDiagnosticEvidence",
        ),
        f"""
        $taskRoot = '{task_root}'
        if (-not $env:USERPROFILE) {{ $env:USERPROFILE = $taskRoot }}
        $fixtureRoot = Join-Path $taskRoot 'fixture'
        $logsRoot = Join-Path $fixtureRoot 'logs/nested'
        $localAppData = Join-Path $taskRoot 'localappdata-diagnostic'
        $stdout = Join-Path $taskRoot 'diagnostic.stdout.log'
        $stderr = Join-Path $taskRoot 'diagnostic.stderr.log'
        $directLog = Join-Path $fixtureRoot 'diagnostics-current.log'
        $nestedLog = Join-Path $logsRoot 'runtime.log'
        $outsideLog = Join-Path $taskRoot 'diagnostics-stale.log'
        New-Item -ItemType Directory -Force -Path $logsRoot,$localAppData | Out-Null
        [IO.File]::WriteAllText($stdout, '')
        [IO.File]::WriteAllText($stderr, '')
        [IO.File]::WriteAllText($nestedLog, 'producer: fixture-log')
        $validText = @"
version: 0.30.0-rc.1
frozen: True
_user_data_root: $fixtureRoot
LOCALAPPDATA: $localAppData
status: OK
"@
        [IO.File]::WriteAllText($directLog, $validText)
        [IO.File]::WriteAllText($outsideLog, $validText)

        $evidence = Read-PackagedDiagnosticEvidence `
          -StdoutPath $stdout `
          -StderrPath $stderr `
          -FixtureRoot $fixtureRoot `
          -ExpectedVersion '0.30.0-rc.1' `
          -LocalAppData $localAppData
        if ($evidence.status -ne 'pass') {{ throw 'Valid direct packaged diagnostic did not pass' }}
        $expectedPaths = @($stdout,$stderr,$directLog,$nestedLog) | ForEach-Object {{ [IO.Path]::GetFullPath($_) }} | Sort-Object
        $actualPaths = @($evidence.evidence_files.path) | Sort-Object
        if (Compare-Object $expectedPaths $actualPaths) {{
          throw "Diagnostic evidence paths escaped or omitted the bounded sources: $($actualPaths -join ', ')"
        }}
        if ($actualPaths -contains [IO.Path]::GetFullPath($outsideLog)) {{
          throw 'An unrelated task-root diagnostic log was consumed'
        }}
        foreach ($file in @($evidence.evidence_files)) {{
          if ($file.sha256 -ne (Get-FileHash -LiteralPath $file.path -Algorithm SHA256).Hash) {{
            throw "Diagnostic evidence hash is inaccurate: $($file.path)"
          }}
        }}

        [IO.File]::WriteAllText($directLog, $validText.Replace('frozen: True','frozen: False'))
        $falseThrew = $false
        try {{
          Read-PackagedDiagnosticEvidence -StdoutPath $stdout -StderrPath $stderr -FixtureRoot $fixtureRoot -ExpectedVersion '0.30.0-rc.1' -LocalAppData $localAppData
        }} catch {{
          $falseThrew = $_.Exception.Message -match 'frozen: True'
        }}
        if (-not $falseThrew) {{
          throw 'Frozen False direct evidence was accepted or an outside stale log satisfied the gate'
        }}

        $canonicalDocuments = Join-Path $env:USERPROFILE 'Documents/CVMAnalytics'
        [IO.File]::WriteAllText($directLog, $validText + "`ncanonical leak: $canonicalDocuments")
        $leakThrew = $false
        try {{
          Read-PackagedDiagnosticEvidence -StdoutPath $stdout -StderrPath $stderr -FixtureRoot $fixtureRoot -ExpectedVersion '0.30.0-rc.1' -LocalAppData $localAppData
        }} catch {{
          $leakThrew = $_.Exception.Message -match 'canonical Documents root'
        }}
        if (-not $leakThrew) {{ throw 'Canonical Documents path leak was accepted' }}
        """,
    )
    assert result.returncode == 0, result.stderr


def test_summary_finalization_persists_final_row_and_accurate_self_metadata(tmp_path: Path) -> None:
    success_root = (tmp_path / "summary-success").as_posix().replace("'", "''")
    failure_root = (tmp_path / "summary-failure").as_posix().replace("'", "''")
    result = _run_powershell_probe(
        tmp_path,
        (
            "Resolve-ApprovedPath",
            "Assert-Descendant",
            "Assert-MutationTargets",
            "Write-EvidenceSummary",
            "Finalize-EvidenceSummary",
        ),
        f"""
        $taskRoot = '{success_root}'
        New-Item -ItemType Directory -Force -Path $taskRoot | Out-Null
        Set-Content -LiteralPath (Join-Path $taskRoot 'artifact.txt') -Value 'artifact'
        Set-Content -LiteralPath (Join-Path $taskRoot 'evidence-summary.json') -Value 'stale-summary'
        $steps = [System.Collections.ArrayList]@()
        $evidence = @{{ status = 'pass'; step_results = $steps }}
        Finalize-EvidenceSummary -Evidence $evidence -StepResults $steps
        $summaryPath = Join-Path $taskRoot 'evidence-summary.json'
        $summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json
        $summaryRow = @($summary.step_results | Where-Object name -eq 'summary')
        if ($summaryRow.Count -ne 1 -or $summaryRow[0].status -ne 'pass' -or $null -eq $summaryRow[0].duration_ms) {{
          throw 'Persisted primary summary does not contain the final passing summary row and duration'
        }}
        if (@($summary.artifact_inventory | Where-Object path -eq $summaryPath).Count -ne 0) {{
          throw 'The evidence summary included a stale self-hash in the normal artifact inventory'
        }}
        if ($summary.summary_metadata.path -ne $summaryPath -or -not $summary.summary_metadata.self_reference) {{
          throw 'Summary self-reference metadata is incomplete'
        }}
        if ([int64]$summary.summary_metadata.bytes -ne (Get-Item -LiteralPath $summaryPath).Length) {{
          throw 'Persisted summary byte metadata is not final and accurate'
        }}

        $taskRoot = '{failure_root}'
        New-Item -ItemType Directory -Force -Path (Join-Path $taskRoot 'evidence-summary.json') | Out-Null
        $failedSteps = [System.Collections.ArrayList]@()
        $failedEvidence = @{{ status = 'failed'; primary_failure = @{{ message = 'original run failure' }}; step_results = $failedSteps }}
        try {{ Finalize-EvidenceSummary -Evidence $failedEvidence -StepResults $failedSteps }} catch {{}}
        $fallbackPath = Join-Path $taskRoot 'evidence-summary-fallback.json'
        if (-not (Test-Path -LiteralPath $fallbackPath)) {{ throw 'Summary write failure did not persist fallback evidence' }}
        $fallback = Get-Content -LiteralPath $fallbackPath -Raw | ConvertFrom-Json
        $failedRow = @($fallback.step_results | Where-Object name -eq 'summary')
        if ($failedRow.Count -ne 1 -or $failedRow[0].status -ne 'failed' -or $null -eq $failedRow[0].duration_ms -or -not $failedRow[0].error) {{
          throw 'Persisted fallback does not contain the final failed summary row, duration, and error'
        }}
        if ([int64]$fallback.summary_metadata.bytes -ne (Get-Item -LiteralPath $fallbackPath).Length) {{
          throw 'Persisted fallback byte metadata is not final and accurate'
        }}
        if ($fallback.primary_failure.message -ne 'original run failure') {{
          throw 'Summary failure replaced the existing primary failure in fallback evidence'
        }}
        $secondary = @($fallback.secondary_failures | Where-Object name -eq 'summary_failure')
        if ($secondary.Count -ne 1 -or -not $secondary[0].message) {{
          throw 'Summary failure was not retained as a durable secondary failure'
        }}
        """,
    )
    assert result.returncode == 0, result.stderr


def test_fixture_after_manifests_are_recorded_with_their_actual_changes() -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")
    main_finalizer = controller.split("if (Test-Path -LiteralPath $fixtureBefore)", 1)[1].split(
        "if (Test-Path -LiteralPath $refreshBefore)", 1
    )[0]
    refresh_finalizer = controller.split("if (Test-Path -LiteralPath $refreshBefore)", 1)[1].split(
        "$evidence.completed_utc", 1
    )[0]

    assert main_finalizer.index("Invoke-RecordedStep -Name 'fixture_classification'") < main_finalizer.index(
        "Write-FileManifest -Root $fixtureRoot"
    ) < main_finalizer.index("Test-FixturePolicy")
    assert "$evidence.fixture_changes = $fixtureClassification.changes" in main_finalizer

    assert refresh_finalizer.index(
        "Invoke-RecordedStep -Name 'refresh_failure_classification'"
    ) < refresh_finalizer.index("Write-FileManifest -Root $refreshFailureRoot") < refresh_finalizer.index(
        "Test-FixturePolicy"
    )
    assert "$evidence.refresh_failure_fixture_changes = $refreshClassification.changes" in refresh_finalizer


def test_refresh_failure_fixture_mutation_uses_exact_python_program_and_records_child(
    tmp_path: Path,
) -> None:
    task_root = tmp_path / "refresh-mutation"
    refresh_root = task_root / "fixture-refresh-failure"
    database = refresh_root / "db" / "cvm_financials.db"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            create table companies (
                cd_cvm integer primary key,
                company_name text not null,
                cnpj text,
                ticker_b3 text,
                company_type text not null default 'comercial',
                is_active integer not null default 1,
                updated_at text not null
            )
            """
        )
        connection.execute(
            "create table app_settings (key text primary key, value text not null, updated_at text not null)"
        )
        connection.execute(
            "insert into companies (cd_cvm, company_name, cnpj, ticker_b3, updated_at) values (?, ?, ?, ?, ?)",
            (9512, "PETROBRAS", "33000167000101", "PETR4", "2026-07-26T00:00:00Z"),
        )
        connection.executemany(
            "insert into app_settings values (?, ?, ?)",
            (
                ("metadata_last_successful_refresh", "1783525990", "2026-07-26T00:00:00Z"),
                ("unrelated_setting", "keep-me", "2026-07-26T00:00:00Z"),
            ),
        )

    result = _run_powershell_probe(
        tmp_path,
        (
            "Resolve-ApprovedPath",
            "Assert-Descendant",
            "Assert-MutationTargets",
            "Assert-ExistingDescendant",
            "Invoke-RefreshFailureFixtureMutation",
        ),
        f"""
        $taskRoot = '{task_root.as_posix()}'
        $refreshFailureRoot = '{refresh_root.as_posix()}'
        $repoRoot = '{ROOT.as_posix()}'
        $evidence = Invoke-RefreshFailureFixtureMutation -DatabasePath '{database.as_posix()}' -SentinelCdCvm 999999 -RepoRoot $repoRoot
        if ($evidence.exit_code -ne 0 -or -not $evidence.pid) {{
          throw 'Refresh mutation child PID/exit evidence is incomplete'
        }}
        if ($evidence.sentinel_cd_cvm -ne 999999 -or
            -not $evidence.mutation_state.precondition_sentinel_absent -or
            $evidence.mutation_state.resolver_mapping_present -or
            -not $evidence.mutation_state.sentinel_inserted) {{
          throw 'Synthetic sentinel mutation provenance is incomplete'
        }}
        foreach ($artifact in @($evidence.program,$evidence.stdout,$evidence.stderr)) {{
          if (-not (Test-Path -LiteralPath $artifact)) {{ throw "Missing refresh mutation artifact: $artifact" }}
        }}
        $preconditionThrew = $false
        try {{
          Invoke-RefreshFailureFixtureMutation -DatabasePath '{database.as_posix()}' -SentinelCdCvm 999999 -RepoRoot $repoRoot | Out-Null
        }} catch {{
          $preconditionThrew = $_.Exception.Data['exit_code'] -ne 0 -and $_.Exception.Data['details'].sentinel_cd_cvm -eq 999999
        }}
        if (-not $preconditionThrew) {{ throw 'Pre-existing synthetic sentinel was accepted' }}
        """,
    )
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "select company_name, cnpj, ticker_b3, company_type, is_active, updated_at from companies where cd_cvm = ?",
            (999999,),
        ).fetchone() == (
            "CVMANALYTICS REFRESH FAILURE SENTINEL",
            None,
            None,
            "comercial",
            1,
            "1970-01-01T00:00:00Z",
        )
        assert connection.execute(
            "select cnpj, ticker_b3 from companies where cd_cvm = ?", (9512,)
        ).fetchone() == ("33000167000101", "PETR4")
        assert connection.execute(
            "select value from app_settings where key = ?",
            ("metadata_last_successful_refresh",),
        ).fetchone() is None
        assert connection.execute(
            "select value from app_settings where key = ?", ("unrelated_setting",)
        ).fetchone() == ("keep-me",)
    controller = CONTROLLER.read_text(encoding="utf-8")
    new_fixture = controller.split("function New-Fixture", 1)[1].split(
        "function Test-InputContract", 1
    )[0]
    assert "Invoke-RefreshFailureFixtureMutation" in new_fixture
    assert "-SentinelCdCvm $refreshFailureSentinelCdCvm" in new_fixture
    assert new_fixture.count("& python -c") == 1
    assert "select cnpj from companies" in new_fixture


def test_refresh_failure_state_probe_is_read_only_argument_safe_and_auditable(
    tmp_path: Path,
) -> None:
    task_root = tmp_path / "refresh failure probe"
    refresh_root = task_root / "fixture refresh failure"
    database = refresh_root / "db with spaces" / "cvm financials.db"
    database.parent.mkdir(parents=True)
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("pragma journal_mode=wal").fetchone() == ("wal",)
        connection.execute("create table companies (cd_cvm integer primary key, cnpj text)")
        connection.execute("create table app_settings (key text primary key, value text)")
        connection.commit()
        connection.execute("pragma wal_checkpoint(truncate)")
        connection.execute("insert into companies values (?, ?)", (999999, None))
        connection.execute(
            "insert into app_settings values (?, ?)", ("unrelated_setting", "keep-me")
        )
        connection.commit()
        assert database.with_name(database.name + "-wal").is_file()
        primary_before = database.read_bytes()

        result = _run_powershell_probe(
            tmp_path,
            (
                "Resolve-ApprovedPath",
                "Assert-Descendant",
                "Assert-MutationTargets",
                "Assert-ExistingDescendant",
                "Read-RefreshFailureStateProbeResult",
                "Invoke-RefreshFailureStateProbe",
            ),
            f"""
            $taskRoot = '{task_root.as_posix()}'
            $refreshFailureRoot = '{refresh_root.as_posix()}'
            $database = '{database.as_posix()}'
            $probe = Invoke-RefreshFailureStateProbe -DatabasePath $database -SentinelCdCvm 999999
            if ($probe.exit_code -ne 0 -or -not $probe.pid -or -not $probe.state.exists) {{
              throw 'Refresh-failure state probe did not return live WAL-backed state'
            }}
            if ($probe.sentinel_cd_cvm -ne 999999 -or $probe.state.sentinel_cd_cvm -ne 999999) {{
              throw 'Refresh-failure state probe did not record the synthetic sentinel ID'
            }}
            if ($null -ne $probe.state.cnpj -or $null -ne $probe.state.metadata_last_successful_refresh) {{
              throw 'Refresh-failure state probe returned the wrong fixture state'
            }}
            foreach ($name in @('program','database','stdout','stderr')) {{
              if (-not $probe[$name]) {{ throw "Missing successful child evidence: $name" }}
            }}
            foreach ($artifact in @($probe.program,$probe.stdout,$probe.stderr)) {{
              if (-not (Test-Path -LiteralPath $artifact)) {{ throw "Missing probe artifact: $artifact" }}
              Assert-Descendant -Parent $taskRoot -Child $artifact
            }}
            $programText = Get-Content -LiteralPath $probe.program -Raw
            if ($programText -notmatch 'as_uri\\(\\)' -or $programText -notmatch 'mode=ro' -or $programText -match 'immutable=1') {{
              throw 'Probe does not use a URI-safe read-only SQLite connection'
            }}

            $brokenDatabase = Join-Path $refreshFailureRoot 'db with spaces/broken.db'
            [IO.File]::WriteAllBytes($brokenDatabase, [byte[]]@())
            $nonzeroThrew = $false
            try {{
              Invoke-RefreshFailureStateProbe -DatabasePath $brokenDatabase -SentinelCdCvm 999999 | Out-Null
            }} catch {{
              $nonzeroThrew = $_.Exception.Data['exit_code'] -ne 0
              foreach ($name in @('pid','exit_code','program','database','stdout','stderr')) {{
                if ($null -eq $_.Exception.Data[$name]) {{ throw "Nonzero failure lacks child evidence: $name" }}
              }}
            }}
            if (-not $nonzeroThrew) {{ throw 'Nonzero state-probe child was accepted' }}

            $stdout = Join-Path $taskRoot 'refresh-failure-state-probe.stdout.log'
            $stderr = Join-Path $taskRoot 'refresh-failure-state-probe.stderr.log'
            [IO.File]::WriteAllText($stdout, '{{not-json')
            [IO.File]::WriteAllText($stderr, '')
            $malformedThrew = $false
            try {{
              Read-RefreshFailureStateProbeResult `
                -ChildPid 777 `
                -ExitCode 0 `
                -ProgramPath $probe.program `
                -DatabasePath $database `
                -SentinelCdCvm 999999 `
                -StdoutPath $stdout `
                -StderrPath $stderr | Out-Null
            }} catch {{
              $malformedThrew = $_.Exception.Message -match 'JSON'
              foreach ($name in @('pid','exit_code','program','database','stdout','stderr')) {{
                if ($null -eq $_.Exception.Data[$name]) {{ throw "Malformed JSON failure lacks child evidence: $name" }}
              }}
            }}
            if (-not $malformedThrew) {{ throw 'Malformed state-probe JSON was accepted' }}
            """,
        )
        assert result.returncode == 0, result.stderr
        assert database.read_bytes() == primary_before
    finally:
        connection.close()

    controller = CONTROLLER.read_text(encoding="utf-8")
    refresh_startup = controller.split("function Test-RefreshFailureStartup", 1)[1].split(
        "function Test-WorkbookOpen", 1
    )[0]
    assert "Invoke-RefreshFailureStateProbe" in refresh_startup
    assert "post_probe = $postProbe" in refresh_startup
    assert "& python -c" not in refresh_startup


def test_refresh_sentinel_preserves_main_ui_company_binding() -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")
    assert re.search(r"\[int\]\$CdCvm\s*=\s*9512", controller)
    assert "$refreshFailureSentinelCdCvm = 999999" in controller
    wait_for_cdp = controller.split("function Wait-ForCdpBridge", 1)[1].split(
        "function Invoke-PackagedUi", 1
    )[0]
    assert "'--cd-cvm', $CdCvm" in wait_for_cdp
    new_fixture = controller.split("function New-Fixture", 1)[1].split(
        "function Test-InputContract", 1
    )[0]
    assert "Representative company row is missing from fixture: $CdCvm" in new_fixture
    assert "-SentinelCdCvm $refreshFailureSentinelCdCvm" in new_fixture
    refresh_startup = controller.split("function Test-RefreshFailureStartup", 1)[1].split(
        "function Test-WorkbookOpen", 1
    )[0]
    assert "-SentinelCdCvm $refreshFailureSentinelCdCvm" in refresh_startup
    assert "$postProbe.state.cnpj -ne $null" in refresh_startup
    assert "$postProbe.state.metadata_last_successful_refresh -ne $null" in refresh_startup
    assert "Offline refresh failure unexpectedly persisted metadata_last_successful_refresh" in refresh_startup


def test_summary_inventory_classifies_locked_artifact_without_losing_primary_failure(
    tmp_path: Path,
) -> None:
    task_root = (tmp_path / "locked-summary").as_posix().replace("'", "''")
    result = _run_powershell_probe(
        tmp_path,
        (
            "Resolve-ApprovedPath",
            "Assert-Descendant",
            "Assert-MutationTargets",
            "Write-EvidenceSummary",
            "Finalize-EvidenceSummary",
        ),
        f"""
        $taskRoot = '{task_root}'
        New-Item -ItemType Directory -Force -Path $taskRoot | Out-Null
        $lockedPath = Join-Path $taskRoot 'validation-run.log'
        [IO.File]::WriteAllText($lockedPath, 'live tee output')
        $stream = [IO.File]::Open($lockedPath, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        try {{
          $steps = [System.Collections.ArrayList]@()
          $evidence = @{{
            status = 'failed'
            primary_failure = @{{ message = 'fixture mutation failed' }}
            step_results = $steps
          }}
          Finalize-EvidenceSummary -Evidence $evidence -StepResults $steps
        }} finally {{
          $stream.Dispose()
        }}
        $summaryPath = Join-Path $taskRoot 'evidence-summary.json'
        if (-not (Test-Path -LiteralPath $summaryPath)) {{ throw 'Locked artifact prevented durable failure summary' }}
        $summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json
        if ($summary.status -ne 'failed' -or $summary.primary_failure.message -ne 'fixture mutation failed') {{
          throw 'Durable summary lost or converted the primary Mode Run failure'
        }}
        $locked = @($summary.artifact_inventory | Where-Object path -eq $lockedPath)
        if ($locked.Count -ne 1 -or $locked[0].status -ne 'hash_unavailable' -or $locked[0].sha256 -or -not $locked[0].error) {{
          throw 'Locked artifact did not receive explicit hash_unavailable evidence'
        }}
        if ([int64]$locked[0].bytes -ne (Get-Item -LiteralPath $lockedPath).Length) {{
          throw 'Locked artifact byte evidence is inaccurate'
        }}
        """,
    )
    assert result.returncode == 0, result.stderr


def test_failure_producers_and_summary_timing_are_structurally_bound() -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")

    def function_body(name: str, next_name: str) -> str:
        return controller.split(f"function {name}", 1)[1].split(f"function {next_name}", 1)[0]

    recorded = function_body("Invoke-RecordedStep", "Write-EvidenceSummary")
    assert "Exception.Data['pid']" in recorded
    assert "Exception.Data['exit_code']" in recorded
    assert "Exception.Data['stdout']" in recorded
    assert "Exception.Data['stderr']" in recorded
    assert "Exception.Data['details']" in recorded

    for function_name, next_name in (
        ("Invoke-IsolatedDiagnostic", "Wait-ForCdpBridge"),
        ("Invoke-PackagedUi", "Test-RefreshFailureStartup"),
        ("Test-RefreshFailureStartup", "Test-WorkbookOpen"),
        ("Invoke-ScratchUpdaterTest", "Compare-PreservationManifest"),
    ):
        assert "Set-ExceptionProcessData" in function_body(function_name, next_name)

    summary = function_body("Finalize-EvidenceSummary", "Assert-ExistingDescendant")
    provisional_write = summary.index("Write-EvidenceSummary -Evidence $Evidence -SummaryPath $summaryPath")
    pass_status = summary.index("$summaryStep.status = 'pass'")
    duration = summary.index("$summaryStep.duration_ms", pass_status)
    final_write = summary.index("Write-EvidenceSummary -Evidence $Evidence -SummaryPath $summaryPath", provisional_write + 1)
    assert provisional_write < pass_status < duration < final_write


def test_updater_stub_compiler_runs_in_windows_powershell_child(tmp_path: Path) -> None:
    if sys.platform != "win32":
        return
    task_root = (tmp_path / "compile-stubs").as_posix().replace("'", "''")
    result = _run_powershell_probe(
        tmp_path,
        (
            "Resolve-ApprovedPath",
            "Assert-Descendant",
            "Assert-MutationTargets",
            "Add-HiddenWindowStyle",
            "Compile-UpdaterStub",
        ),
        f"""
        $taskRoot = '{task_root}'
        New-Item -ItemType Directory -Force -Path $taskRoot | Out-Null
        $oldPath = Join-Path $taskRoot 'old/CVMAnalytics.exe'
        $stagedPath = Join-Path $taskRoot 'staged/CVMAnalytics.exe'
        $oldCompile = Compile-UpdaterStub -ClassName 'OldProgram' -Marker 'old' -OutputPath $oldPath
        $stagedCompile = Compile-UpdaterStub -ClassName 'StagedProgram' -Marker 'staged' -OutputPath $stagedPath
        foreach ($compile in @($oldCompile,$stagedCompile)) {{
          if ($compile.exit_code -ne 0 -or -not $compile.pid -or -not (Test-Path -LiteralPath $compile.source)) {{
            throw 'Stub compile evidence is incomplete'
          }}
          foreach ($artifact in @($compile.output,$compile.stdout,$compile.stderr)) {{
            if (-not (Test-Path -LiteralPath $artifact)) {{ throw "Missing compile artifact: $artifact" }}
          }}
        }}
        if ($oldCompile.sha256 -eq $stagedCompile.sha256) {{ throw 'Old and staged stub executables are not distinct' }}
        foreach ($case in @(@{{ path = $oldPath; marker = 'old' }}, @{{ path = $stagedPath; marker = 'staged' }})) {{
          & $case.path
          if ($LASTEXITCODE -ne 0) {{ throw "Compiled stub failed: $($case.path)" }}
          $markerPath = Join-Path (Split-Path -Parent $case.path) 'relaunch.marker'
          if ((Get-Content -LiteralPath $markerPath -Raw).Trim() -cne $case.marker) {{
            throw "Compiled stub wrote the wrong marker: $($case.path)"
          }}
        }}
        """,
    )
    assert result.returncode == 0, result.stderr


def test_updater_executable_swap_verifier_rejects_old_executable_and_marker(tmp_path: Path) -> None:
    task_root = (tmp_path / "swap-verifier").as_posix().replace("'", "''")
    result = _run_powershell_probe(
        tmp_path,
        (
            "Resolve-ApprovedPath",
            "Assert-Descendant",
            "Assert-ExistingDescendant",
            "Test-UpdaterExecutableSwap",
        ),
        f"""
        $taskRoot = '{task_root}'
        $staged = Join-Path $taskRoot 'staged.exe'
        $current = Join-Path $taskRoot 'current.exe'
        $marker = Join-Path $taskRoot 'relaunch.marker'
        New-Item -ItemType Directory -Force -Path $taskRoot | Out-Null
        Set-Content -LiteralPath $staged -Value 'staged executable'
        Set-Content -LiteralPath $current -Value 'old executable'
        [IO.File]::WriteAllText($marker, 'old')
        $expected = (Get-FileHash -LiteralPath $staged -Algorithm SHA256).Hash
        $threw = $false
        try {{
          Test-UpdaterExecutableSwap -ExpectedStagedSha256 $expected -CurrentExecutable $current -RelaunchMarker $marker | Out-Null
        }} catch {{ $threw = $true }}
        if (-not $threw) {{ throw 'Verifier accepted the old executable and old relaunch marker' }}

        Copy-Item -LiteralPath $staged -Destination $current -Force
        [IO.File]::WriteAllText($marker, 'old')
        $threw = $false
        try {{
          Test-UpdaterExecutableSwap -ExpectedStagedSha256 $expected -CurrentExecutable $current -RelaunchMarker $marker | Out-Null
        }} catch {{ $threw = $true }}
        if (-not $threw) {{ throw 'Verifier accepted the old relaunch marker with the staged executable' }}

        Set-Content -LiteralPath $current -Value 'old executable'
        [IO.File]::WriteAllText($marker, 'staged')
        $threw = $false
        try {{
          Test-UpdaterExecutableSwap -ExpectedStagedSha256 $expected -CurrentExecutable $current -RelaunchMarker $marker | Out-Null
        }} catch {{ $threw = $true }}
        if (-not $threw) {{ throw 'Verifier accepted the old executable with the staged relaunch marker' }}

        Copy-Item -LiteralPath $staged -Destination $current -Force
        [IO.File]::WriteAllText($marker, 'staged')
        $verified = Test-UpdaterExecutableSwap -ExpectedStagedSha256 $expected -CurrentExecutable $current -RelaunchMarker $marker
        if ($verified.current_executable_sha256 -ne $expected -or $verified.relaunch_marker -cne 'staged') {{
          throw 'Verifier did not return exact staged executable/marker evidence'
        }}
        """,
    )
    assert result.returncode == 0, result.stderr


def test_updater_flow_statically_binds_compilation_and_exact_swap_verification() -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")
    updater = controller.split("function Invoke-ScratchUpdaterTest", 1)[1].split(
        "function Compare-PreservationManifest", 1
    )[0]
    first_compile = updater.index("Compile-UpdaterStub -ClassName 'OldProgram' -Marker 'old'")
    second_compile = updater.index("Compile-UpdaterStub -ClassName 'StagedProgram' -Marker 'staged'")
    staged_hash = updater.index("$stagedExecutableSha256 =")
    helper_launch = updater.index("'-File',$helper,'-New',$staged,'-Current',$current")
    exact_verification = updater.index("Test-UpdaterExecutableSwap")
    assert first_compile < second_compile < staged_hash < helper_launch < exact_verification
    assert "old_compile" in updater and "staged_compile" in updater
    assert "current_executable_sha256" in updater and "relaunch_marker" in updater

    compiler = controller.split("function Compile-UpdaterStub", 1)[1].split("function ", 1)[0]
    assert "powershell.exe" in compiler
    assert "-EncodedCommand" in compiler
    assert "Assert-MutationTargets" in compiler


def test_node_finalizer_close_failure_is_persisted_and_exits_nonzero(tmp_path: Path) -> None:
    output_dir = tmp_path / "node-close-failure"
    script = tmp_path / "node-close-failure-probe.cjs"
    script.write_text(
        textwrap.dedent(
            f"""
            const {{ runValidation }} = require({json.dumps(str(UI_HARNESS))});
            const outputDir = {json.dumps(str(output_dir))};
            const page = {{
              url: () => "file:///candidate/index.html",
              on: () => undefined,
              waitForFunction: async () => undefined,
              evaluate: async (_fn, payload) => {{
                if (payload?.methodName === "get_app_status") {{
                  return {{ runtime: {{ version: "1.2.3", build_commit: "abcdef123456" }} }};
                }}
                throw new Error("unexpected page.evaluate call");
              }},
            }};
            const browser = {{
              contexts: () => [{{ pages: () => [page] }}],
              close: async () => {{ throw new Error("mock browser.close failure"); }},
            }};
            const chromium = {{ connectOverCDP: async () => browser }};
            runValidation({{
              cdpUrl: "http://127.0.0.1:9223",
              outputDir,
              cdCvm: 9512,
              processStartMs: Date.now(),
              expectedVersion: "1.2.3",
              expectedBuildSha: "abcdef123456",
              readinessOnly: true,
            }}, {{ chromium }}).catch((error) => {{
              console.error(error.stack || error.message);
              process.exitCode = 1;
            }});
            """
        ),
        encoding="utf-8",
    )
    result = subprocess.run(["node", str(script)], capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert "mock browser.close failure" in result.stderr
    persisted = json.loads((output_dir / "ui-results.json").read_text(encoding="utf-8"))
    assert persisted["status"] == "failed"
    assert "mock browser.close failure" in persisted["error"]
    assert any(
        item["stage"] == "browser.close" and "mock browser.close failure" in item["error"]
        for item in persisted["node_finalizer_errors"]
    )
