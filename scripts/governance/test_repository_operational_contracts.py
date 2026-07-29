from __future__ import annotations

import ast
import importlib
import json
import re
import subprocess
import textwrap
from fnmatch import fnmatchcase
from pathlib import Path

import yaml

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


def _release_workflow() -> dict[str, object]:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/release-desktop.yml").read_text(encoding="utf-8")
    )
    return workflow.get("on", workflow.get(True))["workflow_dispatch"] | {
        "jobs": workflow["jobs"],
        "permissions": workflow["permissions"],
    }


def _job_step(job: dict[str, object], name: str) -> dict[str, object]:
    steps = [step for step in job["steps"] if step.get("name") == name]
    assert len(steps) == 1, f"expected one {name!r} step"
    return steps[0]


def _run_source(job: dict[str, object]) -> str:
    return "\n".join(str(step.get("run", "")) for step in job.get("steps", []))


def test_release_workflow_has_exact_phase_graph_and_final_only_publish_authority() -> None:
    workflow = _release_workflow()
    jobs = workflow["jobs"]

    assert set(jobs) == {
        "resolve-candidate",
        "build-windows",
        "attest-evidence",
        "publish-preflight",
        "final-publish",
    }
    assert workflow["inputs"]["phase"]["options"] == ["candidate", "attest", "publish"]
    assert jobs["resolve-candidate"]["if"] == "inputs.phase == 'candidate'"
    assert jobs["build-windows"]["if"] == "inputs.phase == 'candidate'"
    assert jobs["build-windows"]["needs"] == "resolve-candidate"
    assert jobs["attest-evidence"]["if"] == "inputs.phase == 'attest'"
    assert jobs["publish-preflight"]["if"] == "inputs.phase == 'publish'"
    assert jobs["final-publish"]["if"] == "inputs.phase == 'publish'"
    assert jobs["final-publish"]["needs"] == "publish-preflight"
    assert workflow["permissions"] == {"contents": "read", "actions": "read"}
    assert jobs["final-publish"]["permissions"] == {
        "contents": "write",
        "actions": "read",
    }
    assert jobs["final-publish"]["environment"] == "release-publication"
    assert sum(job.get("permissions", {}).get("contents") == "write" for job in jobs.values()) == 1
    assert sum("environment" in job for job in jobs.values()) == 1


def test_release_workflow_transports_dispatch_values_as_environment_data_not_shell_code() -> None:
    workflow = _release_workflow()
    jobs = workflow["jobs"]
    dispatch_expressions = "${{ inputs."

    assert all(dispatch_expressions not in _run_source(job) for job in jobs.values())
    assert jobs["resolve-candidate"]["env"] == {
        "RELEASE_VERSION": "${{ inputs.version }}",
        "CANDIDATE_SHA": "${{ inputs.candidate_sha }}",
    }
    assert jobs["publish-preflight"]["env"] == {
        "RELEASE_VERSION": "${{ inputs.version }}",
        "CANDIDATE_SHA": "${{ inputs.candidate_sha }}",
        "CANDIDATE_RUN_ID": "${{ inputs.candidate_run_id }}",
        "ATTESTATION_RUN_ID": "${{ inputs.attestation_run_id }}",
    }
    attest_env = jobs["attest-evidence"]["env"]
    assert attest_env["RELEASE_VERSION"] == "${{ inputs.version }}"
    assert attest_env["CANDIDATE_SHA"] == "${{ inputs.candidate_sha }}"
    assert attest_env["CANDIDATE_RUN_ID"] == "${{ inputs.candidate_run_id }}"
    assert all(value.startswith("${{ inputs.") for value in attest_env.values())


def test_release_workflow_binds_candidate_and_trusted_attestation_producers_in_exact_steps() -> None:
    workflow = _release_workflow()
    jobs = workflow["jobs"]
    attest = _job_step(jobs["attest-evidence"], "Verify candidate binding and write trusted attestations")["run"]
    publish = _job_step(jobs["publish-preflight"], "Fetch and verify candidate-bound evidence attestations")["run"]
    candidate = _job_step(jobs["publish-preflight"], "Re-resolve exact candidate, CI, and candidate artifact identities")["run"]

    assert '$env:GITHUB_REF -ne "refs/heads/main"' in attest
    assert "$env:GITHUB_SHA.Trim().ToLowerInvariant() -ne $candidateSha" in attest
    assert all(token in attest for token in (
        '$candidateRun.name -ne "Release Desktop"',
        '$candidateRun.path -ne ".github/workflows/release-desktop.yml"',
        '$candidateRun.event -ne "workflow_dispatch"',
        '$candidateRun.conclusion -ne "success"',
        '$candidateRun.head_branch -ne "main"',
        '$candidateRun.head_sha -ne $candidateSha',
        'candidatePayload.package_artifact.id',
        'candidatePayload.package_artifact.checksum',
        'release-evidence-attestation-$Type.json',
        'workflow_run_id = "$env:GITHUB_RUN_ID"',
        'phase = "attest"',
    ))
    assert all(token in candidate for token in (
        '$candidateRun.name -ne "Release Desktop"',
        '$candidateRun.path -ne ".github/workflows/release-desktop.yml"',
        '$candidateRun.event -ne "workflow_dispatch"',
        '$candidateRun.conclusion -ne "success"',
        '$candidateRun.head_branch -ne "main"',
        '$candidateRun.head_sha -ne $candidateSha',
    ))
    assert all(token in publish for token in (
        '$attestationRun.name -ne "Release Desktop"',
        '$attestationRun.path -ne ".github/workflows/release-desktop.yml"',
        '$attestationRun.event -ne "workflow_dispatch"',
        '$attestationRun.conclusion -ne "success"',
        '$attestationRun.head_branch -ne "main"',
        '$attestationRun.head_sha -ne $candidateSha',
        'actions/runs/$($metadata.workflow_run.id)',
        '$payload.producer.phase -ne "attest"',
        'release-attestation-manual-local-data-$attestationRunId',
        'release-attestation-manual-packaged-$attestationRunId',
        'release-attestation-conditional-api-$attestationRunId',
        'release-attestation-conditional-ccee-$attestationRunId',
        'release-attestation-conditional-strict-backup-$attestationRunId',
    ))


def test_release_workflow_keeps_candidate_evidence_and_publish_preflight_immutable() -> None:
    workflow = _release_workflow()
    jobs = workflow["jobs"]
    evidence_step = _job_step(jobs["build-windows"], "Write candidate evidence")["run"]
    preflight = jobs["publish-preflight"]
    final_publish = jobs["final-publish"]

    assert all(token in evidence_step for token in (
        "schema_version",
        "candidate_sha",
        "tag_target_sha",
        "candidate_run_id",
        "package_artifact",
        "zip_sha256",
        "observed_build_sha",
    ))
    assert "verified-release-evidence.json" in _run_source(preflight)
    assert "Get-FileHash" in _run_source(preflight)
    assert all(
        "build_desktop.ps1" not in str(step)
        and "Compress-Archive" not in str(step)
        and "softprops/action-gh-release" not in str(step)
        for step in preflight["steps"]
    )
    assert any("softprops/action-gh-release" in step.get("uses", "") for step in final_publish["steps"])


def test_release_workflow_expiry_recovery_requires_a_fresh_superseding_candidate_cycle() -> None:
    workflow = _release_workflow()
    jobs = workflow["jobs"]
    attest = _run_source(jobs["attest-evidence"])
    publish = _run_source(jobs["publish-preflight"])
    release_process = (ROOT / "docs/release-process.md").read_text(encoding="utf-8")
    build_release = (ROOT / "docs/build-release.md").read_text(encoding="utf-8")

    assert "-not $_.expired" in attest
    assert "-not $_.expired" in publish
    for document in (release_process, build_release):
        document = re.sub(r"\s+", " ", document.replace("**", " "))
        assert "same version/SHA only after artifact expiry" in document
        assert "new immutable artifacts and run IDs" in document
        assert "superseded evidence" in document
        assert "repeat exact-SHA CI, package/manual/conditional attestations, and #440 approval" in document


def test_release_workflow_preserves_updater_version_grammar() -> None:
    workflow = _release_workflow()
    jobs = workflow["jobs"]
    version_number = r"(?:0|[1-9][0-9]*)"
    version_pattern = rf"^{version_number}\.{version_number}\.{version_number}(?:-rc\.{version_number})?$"
    powershell_pattern = (
        "'^(?:0|[1-9][0-9]*)\\.(?:0|[1-9][0-9]*)\\.(?:0|[1-9][0-9]*)"
        "(?:-rc\\.(?:0|[1-9][0-9]*))?$'"
    )
    validation_steps = (
        _job_step(jobs["resolve-candidate"], "Resolve exact tag target and latest exact-SHA main CI"),
        _job_step(jobs["attest-evidence"], "Verify candidate binding and write trusted attestations"),
        _job_step(jobs["publish-preflight"], "Re-resolve exact candidate, CI, and candidate artifact identities"),
        _job_step(jobs["final-publish"], "Verify the same candidate artifact, tag, and latest CI after approval"),
    )

    assert all(powershell_pattern in step["run"] for step in validation_steps)
    assert re.fullmatch(version_pattern, "0.0.0")
    assert re.fullmatch(version_pattern, "1.2.3-rc.12")
    for invalid in ("01.2.3", "1.02.3", "1.2.03", "1.2.3-rc.01", "1.2.3-beta"):
        assert not re.fullmatch(version_pattern, invalid)


def test_release_and_ci_actions_are_full_sha_pinned() -> None:
    for relative_path in (".github/workflows/release-desktop.yml", ".github/workflows/ci.yml"):
        workflow = yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))
        jobs = workflow["jobs"]
        uses = [
            step["uses"]
            for job in jobs.values()
            for step in job.get("steps", [])
            if "uses" in step
        ]
        assert uses, relative_path
        assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", action) for action in uses)


def test_release_workflow_keeps_publish_write_only_and_never_rebuilds_or_retags() -> None:
    workflow = _release_workflow()
    final_publish = workflow["jobs"]["final-publish"]
    final_steps = final_publish["steps"]
    final_source = _run_source(final_publish)

    assert set(workflow) == {"inputs", "jobs", "permissions"}
    assert [step["name"] for step in final_steps if step.get("uses", "").startswith("actions/download-artifact@")] == [
        "Download immutable candidate package",
        "Download immutable candidate evidence",
        "Download verified manual evidence binding",
    ]
    assert _job_step(final_publish, "Publish GitHub Release from verified candidate only")["uses"].startswith(
        "softprops/action-gh-release@"
    )
    assert "build_desktop.ps1" not in final_source
    assert "Compress-Archive" not in final_source
    assert "git tag " not in final_source
