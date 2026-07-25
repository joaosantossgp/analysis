from __future__ import annotations

import re
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
        "Stop-Process -Id $p.Id -Force",
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
        "process.exit(1)",
    ):
        assert token in ui_harness, f"UI harness contract missing: {token}"
