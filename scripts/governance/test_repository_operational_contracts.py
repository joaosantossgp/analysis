from __future__ import annotations

import ast
import importlib
import json
import re
import subprocess
import textwrap
from fnmatch import fnmatchcase
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _tracked_files() -> set[str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return set(result.stdout.splitlines())


def _tracked_matches(pattern: str, tracked_files: set[str]) -> set[str]:
    return {path for path in tracked_files if fnmatchcase(path, pattern)}


def _extract_python_heredoc(workflow: str) -> str:
    pattern = re.compile(
        r"(?ms)^[ \t]*python - <<'PY'[ \t]*\n(?P<body>.*?)^[ \t]*PY[ \t]*$"
    )
    matches = list(pattern.finditer(workflow))
    assert len(matches) == 1, "expected exactly one embedded Python heredoc"
    return textwrap.dedent(matches[0].group("body"))


def _import_from_symbols(source: str) -> set[tuple[str, str]]:
    tree = ast.parse(source)
    return {
        (node.module, alias.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
        for alias in node.names
    }


def test_seed_import_inventory_ignores_textual_decoys() -> None:
    source = """
message = "from src.platform.db import build_engine"
# from src.platform.settings import build_settings
from src.platform.settings import build_settings
"""

    assert _import_from_symbols(source) == {
        ("src.platform.settings", "build_settings")
    }


def test_seed_catalog_smoke_uses_resolvable_platform_modules() -> None:
    workflow = (ROOT / ".github/workflows/seed_catalog.yml").read_text(
        encoding="utf-8"
    )
    imports = _import_from_symbols(_extract_python_heredoc(workflow))
    expected_imports = {
        ("src.platform.db", "build_engine"),
        ("src.platform.settings", "build_settings"),
    }
    stale_imports = {
        ("src.db", "build_engine"),
        ("src.settings", "build_settings"),
    }

    violations = [
        f"stale seed import: from {module_name} import {symbol_name}"
        for module_name, symbol_name in sorted(imports & stale_imports)
    ]
    violations.extend(
        f"missing active seed import: from {module_name} import {symbol_name}"
        for module_name, symbol_name in sorted(expected_imports - imports)
    )
    assert not violations, "\n".join(violations)
    for module_name, symbol_name in expected_imports:
        symbol = getattr(importlib.import_module(module_name), symbol_name)
        assert callable(symbol)


def test_policy_wildcards_resolve_to_tracked_runtime_files() -> None:
    tracked_files = _tracked_files()

    read_service_matches = _tracked_matches(
        "src/financials/read_service_*.py", tracked_files
    )
    bridge_api_matches = _tracked_matches("desktop/bridge_api/**", tracked_files)

    assert "src/financials/read_service_query.py" in read_service_matches
    assert "desktop/bridge_api/base.py" in bridge_api_matches
    assert not _tracked_matches("desktop/missing_bridge_api/**", tracked_files)


def test_critical_runtime_policy_tracks_active_module_paths() -> None:
    policy = json.loads(
        (ROOT / ".github/guardrails/path-policy.json").read_text(encoding="utf-8")
    )
    group = next(
        item for item in policy["criticalGroups"] if item["name"] == "critical-runtime"
    )
    patterns = set(group["patterns"])
    stale = {
        "src/settings.py",
        "src/db.py",
        "src/database.py",
        "src/query_layer.py",
        "src/read_service.py",
        "src/refresh_service.py",
        "src/scraper.py",
    }
    required = {
        "src/platform/settings.py",
        "src/platform/db.py",
        "src/financials/database.py",
        "src/financials/query_layer.py",
        "src/financials/read_service.py",
        "src/financials/read_service_*.py",
        "src/refresh/service.py",
        "src/financials/scraper.py",
        "apps/api/app/main.py",
        "apps/api/app/dependencies.py",
        "desktop/app.py",
        "desktop/bridge.py",
        "desktop/services.py",
        "desktop/bridge_api/**",
    }

    violations = [f"stale path-policy entry: {path}" for path in sorted(patterns & stale)]
    violations.extend(
        f"missing active path-policy entry: {path}" for path in sorted(required - patterns)
    )
    tracked_files = _tracked_files()
    violations.extend(
        f"path-policy entry matches no tracked file: {path}"
        for path in sorted(patterns)
        if not _tracked_matches(path, tracked_files)
    )
    assert not violations, "\n".join(violations)


def test_worktree_lifecycle_scripts_default_to_main() -> None:
    for relative_path in (
        "scripts/governance/worktree_create.ps1",
        "scripts/governance/worktree_remove.ps1",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8-sig")
        match = re.search(r'\[string\]\$Base\s*=\s*"([^"]+)"', source)
        assert match is not None, relative_path
        assert match.group(1) == "main", relative_path


def _workflow_run_blocks(workflow: str) -> list[str]:
    return re.findall(
        r"(?ms)^\s*run:\s*\|\s*\n(?P<body>.*?)(?=^\s*- name:|^\s*- uses:|^\s*\w[\w-]*:|\Z)",
        workflow,
    )


def test_release_workflow_uses_env_transport_for_all_dispatch_inputs() -> None:
    workflow = (ROOT / ".github/workflows/release-desktop.yml").read_text(
        encoding="utf-8"
    )
    run_source = "\n".join(_workflow_run_blocks(workflow))
    expected_env_names = {
        "RELEASE_VERSION",
        "CANDIDATE_SHA",
        "CANDIDATE_RUN_ID",
        "ATTESTATION_RUN_ID",
    }

    assert "${{ inputs." not in run_source
    assert all(f"{name}: ${{{{ inputs." in workflow for name in expected_env_names)
    assert all(f"$env:{name}" in run_source for name in expected_env_names)


def test_release_workflow_keeps_adversarial_dispatch_values_out_of_shell_source() -> None:
    workflow = (ROOT / ".github/workflows/release-desktop.yml").read_text(
        encoding="utf-8"
    )
    run_source = "\n".join(_workflow_run_blocks(workflow))
    adversarial_quote_newline = '"; throw "dispatch injection"\n#'

    # Workflow expressions are rendered before PowerShell parses `run:`. The
    # regression is that no dispatch expression can enter that parse boundary;
    # it must first become an environment value and then be read as data.
    assert "${{ inputs." not in run_source
    assert adversarial_quote_newline not in run_source
    assert "RELEASE_VERSION: ${{ inputs.version }}" in workflow
    assert "$env:RELEASE_VERSION" in run_source


def test_release_workflow_requires_candidate_bound_evidence_attestations() -> None:
    workflow = (ROOT / ".github/workflows/release-desktop.yml").read_text(
        encoding="utf-8"
    )
    required_fragments = (
        "release-evidence-attestation.json",
        "schema_version",
        "attestation_type",
        "candidate_sha",
        "tag_target_sha",
        "candidate_run_id",
        "package_artifact_id",
        "zip_checksum",
        "workflow_run_id",
        "$payload.result.manual",
        "$payload.result.summary",
        "decision.status",
        "candidate-diff",
        "release-policy",
        "verified-release-evidence.json",
        "Get-FileHash",
        "actions/artifacts/$ArtifactId/zip",
    )
    missing = [fragment for fragment in required_fragments if fragment not in workflow]

    assert not missing, f"release evidence contract missing: {', '.join(missing)}"
    assert "local_data_evidence_ref" not in workflow
    assert "api_evidence_basis:" not in workflow


def test_release_workflow_only_accepts_trusted_attestation_producer_runs() -> None:
    workflow = (ROOT / ".github/workflows/release-desktop.yml").read_text(
        encoding="utf-8"
    )
    required_fragments = (
        "attest-evidence:",
        "inputs.phase == 'attest'",
        "ATTESTATION_RUN_ID: ${{ inputs.attestation_run_id }}",
        'producer = [ordered]@{ workflow_run_id = "$env:GITHUB_RUN_ID"; phase = "attest"',
        "actions/runs/$($metadata.workflow_run.id)",
        '$producerRun.name -ne "Release Desktop"',
        '$producerRun.path -ne ".github/workflows/release-desktop.yml"',
        '$producerRun.event -ne "workflow_dispatch"',
        '$producerRun.conclusion -ne "success"',
        '$producerRun.head_branch -ne "main"',
        '$producerRun.head_sha -ne $candidateSha',
        '$payload.producer.phase -ne "attest"',
        "release-attestation-manual-local-data-",
        "release-attestation-manual-packaged-",
        "release-attestation-conditional-api-",
        "release-attestation-conditional-ccee-",
        "release-attestation-conditional-strict-backup-",
    )
    missing = [fragment for fragment in required_fragments if fragment not in workflow]

    assert not missing, f"trusted attestation producer checks missing: {', '.join(missing)}"
    assert "LOCAL_DATA_EVIDENCE_ARTIFACT_ID" not in workflow


def test_release_workflow_preserves_updater_version_grammar() -> None:
    workflow = (ROOT / ".github/workflows/release-desktop.yml").read_text(
        encoding="utf-8"
    )
    version_number = r"(?:0|[1-9][0-9]*)"
    version_pattern = rf"^{version_number}\.{version_number}\.{version_number}(?:-rc\.{version_number})?$"

    assert version_pattern in workflow
    assert re.fullmatch(version_pattern, "0.0.0")
    assert re.fullmatch(version_pattern, "1.2.3-rc.12")
    for invalid in ("01.2.3", "1.02.3", "1.2.03", "1.2.3-rc.01", "1.2.3-beta"):
        assert not re.fullmatch(version_pattern, invalid)


def test_release_and_ci_actions_are_full_sha_pinned() -> None:
    for relative_path in (".github/workflows/release-desktop.yml", ".github/workflows/ci.yml"):
        workflow = (ROOT / relative_path).read_text(encoding="utf-8")
        uses = re.findall(
            r"(?m)^\s*(?:-\s+)?uses:\s*([^\s#]+)(?:\s+#\s*(.+))?$",
            workflow,
        )
        assert uses, relative_path
        for action, comment in uses:
            assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", action), action
            assert comment is not None and re.fullmatch(r"v\d+(?:\.\d+){1,2}", comment), action


def test_release_workflow_keeps_publish_write_only_and_never_rebuilds_or_retags() -> None:
    workflow = (ROOT / ".github/workflows/release-desktop.yml").read_text(
        encoding="utf-8"
    )
    final_publish = workflow.split("  final-publish:", maxsplit=1)[1]

    assert "push:\n    tags:" not in workflow
    assert workflow.count("contents: write") == 1
    assert "environment: release-publication" in final_publish
    assert "actions/download-artifact@" in final_publish
    assert "build_desktop.ps1" not in final_publish
    assert "Compress-Archive" not in final_publish
    assert "git tag " not in final_publish
