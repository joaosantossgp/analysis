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


_THROW_GUARD = re.compile(
    r"if\s*\((?P<condition>[^\n{}()]*(?:\([^\n{}()]*\)[^\n{}()]*)*)\)\s*\{\s*throw\b",
    re.MULTILINE,
)
_PS_COMPARISON = re.compile(
    r"(?P<left>(?:\[string\])?\$[\w:]+(?:\.\w+)*)\s*"
    r"(?P<operator>-ne|-eq)\s*"
    r'(?P<right>"[^"]*"|\d+|(?:\[string\])?\$[\w:]+(?:\.\w+)*)'
)


def _throw_guard(script: str, required_member: str) -> str:
    executable_source = re.sub(r"(?m)^\s*#.*$", "", script)
    executable_source = re.sub(r"'[^']*'", "'literal'", executable_source)
    guards = [
        match.group("condition")
        for match in _THROW_GUARD.finditer(executable_source)
        if required_member in match.group("condition")
    ]
    assert len(guards) == 1, f"expected one executable throw guard for {required_member}"
    return guards[0]


def _guard_rejects(guard: str, fixture: dict[str, str]) -> bool:
    comparisons = list(_PS_COMPARISON.finditer(guard))
    assert comparisons, f"no supported PowerShell comparisons in guard: {guard}"
    assert "-and" not in guard, f"reject guard must not weaken mismatches with -and: {guard}"
    assert all(match.group("operator") == "-ne" for match in comparisons)
    assert guard.count("-or") >= len(comparisons) - 1

    def value(token: str) -> str:
        token = token.removeprefix("[string]")
        if token.startswith('"'):
            return token[1:-1]
        if token.isdecimal():
            return token
        return fixture[token]

    return any(value(match.group("left")) != value(match.group("right")) for match in comparisons)


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


def test_release_workflow_power_shell_reject_guards_fail_closed_for_provenance_fixtures() -> None:
    workflow = _release_workflow()
    jobs = workflow["jobs"]
    resolve = _job_step(jobs["resolve-candidate"], "Resolve exact tag target and latest exact-SHA main CI")["run"]
    attest = _job_step(jobs["attest-evidence"], "Verify candidate binding and write trusted attestations")["run"]
    publish = _job_step(jobs["publish-preflight"], "Fetch and verify candidate-bound evidence attestations")["run"]
    final = _job_step(jobs["final-publish"], "Verify the same candidate artifact, tag, and latest CI after approval")["run"]

    tag_guard = _throw_guard(resolve, "$tagTargetSha")
    assert _guard_rejects(tag_guard, {"$tagTargetSha": "drift", "$candidateSha": "candidate"})

    trusted_run_fixture = {
        "$attestationRun.name": "Release Desktop",
        "$attestationRun.path": ".github/workflows/release-desktop.yml",
        "$attestationRun.event": "workflow_dispatch",
        "$attestationRun.conclusion": "success",
        "$attestationRun.head_branch": "main",
        "$attestationRun.head_sha": "candidate",
        "$candidateSha": "candidate",
    }
    trusted_run_guard = _throw_guard(publish, "$attestationRun.name")
    for field, rejected_value in (
        ("$attestationRun.conclusion", "failed"),
        ("$attestationRun.conclusion", "cancelled"),
        ("$attestationRun.name", "Untrusted workflow"),
        ("$attestationRun.path", ".github/workflows/untrusted.yml"),
        ("$attestationRun.head_branch", "release"),
        ("$attestationRun.head_sha", "other-sha"),
    ):
        fixture = trusted_run_fixture | {field: rejected_value}
        assert _guard_rejects(trusted_run_guard, fixture)

    producer_fixture = {
        "$producerRun.name": "Release Desktop",
        "$producerRun.path": ".github/workflows/release-desktop.yml",
        "$producerRun.event": "workflow_dispatch",
        "$producerRun.conclusion": "success",
        "$producerRun.head_branch": "main",
        "$producerRun.head_sha": "candidate",
        "$candidateSha": "candidate",
    }
    producer_guard = _throw_guard(publish, "$producerRun.name")
    assert producer_guard.startswith("$RequireTrustedProducer -and (")
    producer_guard = producer_guard.removeprefix("$RequireTrustedProducer -and (").removesuffix(")")
    assert "Read-ActionArtifactJson $item.id \"release-evidence-attestation.json\"" in publish
    assert _guard_rejects(producer_guard, producer_fixture | {"$producerRun.conclusion": "failed"})
    assert _guard_rejects(producer_guard, producer_fixture | {"$producerRun.path": ".github/workflows/other.yml"})

    artifact_count_guard = _throw_guard(publish, "$matches.Count")
    assert _guard_rejects(artifact_count_guard, {"$matches.Count": "0"})
    assert "Where-Object { $_.name -eq $Name -and -not $_.expired }" in publish
    assert "Resolve-AttestationArtifact \"release-attestation-manual-local-data-$attestationRunId\"" in publish

    package_guard = _throw_guard(publish, "$candidatePayload.package_artifact.id")
    assert _guard_rejects(
        package_guard,
        {
            "$candidatePayload.schema_version": "1",
            "$candidatePayload.candidate.candidate_sha": "candidate",
            "$candidatePayload.candidate.tag_target_sha": "candidate",
            "$candidatePayload.candidate.candidate_run_id": "run",
            "$candidatePayload.candidate.observed_build_sha": "candidate",
            "$candidatePayload.package_artifact.id": "wrong-artifact",
            "$candidateSha": "candidate",
            "$candidateRunId": "run",
            "$env:CANDIDATE_PACKAGE_ARTIFACT_ID": "package-artifact",
        },
    )

    checksum_guard = _throw_guard(final, "$checksum -ne $actual")
    assert _guard_rejects(
        checksum_guard,
        {
            "$checksum": "declared-checksum",
            "$actual": "actual-checksum",
            "$evidence.package_artifact.checksum": "actual-checksum",
        },
    )
    assert "$candidatePayload.package_artifact.checksum -notmatch '^[0-9a-f]{64}$'" in attest


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
        assert "revalidate the latest successful exact-SHA CI" in document
        assert "repeat package/manual/conditional attestations and #440 approval" in document


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
