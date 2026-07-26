from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTROLLER = ROOT / "scripts/diagnostics/validate_packaged_candidate.ps1"
UI_HARNESS = ROOT / "scripts/diagnostics/validate_packaged_ui.cjs"


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
    assert "refresh-failure only permits logs/cache" in controller
    assert "0x80040154" in controller
    finalization = controller.split("} finally {", 1)[-1]
    assert "primary_failure" in finalization
    assert "Write-EvidenceSummary" in finalization


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


def test_execution_block_prepares_fresh_attempt_before_fixture_creation() -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")
    execution = controller.split("Test-InputContract\n", 1)[1]
    assert execution.index("Assert-NoReparseTree -Root $taskRoot") < execution.index("Prepare-RunAttempt") < execution.index("New-Fixture")
    assert "-Policy 'refresh-failure'" in execution
    assert "Representative company row disappeared" in controller
    assert "0x80040154" in controller


def test_failed_run_provenance_is_recorded_inside_finalization() -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")
    ui_harness = UI_HARNESS.read_text(encoding="utf-8")
    execution = controller.split("Test-InputContract\n", 1)[1]
    assert execution.index("$evidence =") < execution.index("Prepare-RunAttempt") < execution.index("Get-Process -Name CVMAnalytics")
    for step in ("attempt_preparation", "fixture_before_manifest", "refresh_before_manifest", "environment_audit", "source_after_preservation", "fixture_classification", "refresh_failure_classification", "summary"):
        assert f"-Name '{step}'" in execution
    assert "Exception.Data['node_pid']" in controller
    assert "Exception.Data['node_exit_code']" in controller
    assert "evidence-summary-fallback.json" in execution
    assert "node_finalizer_errors" in ui_harness
