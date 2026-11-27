from __future__ import annotations

import ast
import importlib
import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path
from urllib.parse import unquote

import yaml

ROOT = Path(__file__).resolve().parents[2]


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
    ):
        fixture = trusted_run_fixture | {field: rejected_value}
        assert _guard_rejects(trusted_run_guard, fixture)
    assert "$attestationWorkflowSourceSha -notmatch '^[0-9a-f]{40}$'" in publish

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
            "$candidatePayload.candidate.workflow_source_sha": "trusted-main-source",
            "$candidatePayload.candidate.candidate_run_id": "run",
            "$candidatePayload.candidate.observed_build_sha": "candidate",
            "$candidatePayload.package_artifact.id": "wrong-artifact",
            "$candidateSha": "candidate",
            "$candidateRunId": "run",
            "$candidateWorkflowSourceSha": "trusted-main-source",
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


def test_release_workflow_attest_remains_candidate_bound_after_main_advances() -> None:
    workflow = _release_workflow()
    jobs = workflow["jobs"]
    attest = _job_step(jobs["attest-evidence"], "Verify candidate binding and write trusted attestations")["run"]
    publish = _job_step(jobs["publish-preflight"], "Fetch and verify candidate-bound evidence attestations")["run"]

    dispatch_guard = _throw_guard(attest, "$env:GITHUB_REF")
    assert _guard_rejects(
        dispatch_guard,
        {"$env:GITHUB_REF": "refs/heads/untrusted"},
    )
    assert "$env:GITHUB_SHA.Trim().ToLowerInvariant() -ne $candidateSha" not in dispatch_guard
    assert "git merge-base --is-ancestor $candidateSha origin/main" in attest
    assert "$workflowSourceSha = $env:GITHUB_SHA.Trim().ToLowerInvariant()" in attest
    assert "workflow_source_sha = $workflowSourceSha" in attest
    assert "$attestationRun.head_sha -ne $candidateSha" not in publish
    assert "$payload.producer.workflow_source_sha -ne $WorkflowSourceSha" in publish
    assert "$payload.candidate.package_artifact_id -ne $PackageArtifactId" in publish


def test_release_workflow_recovery_carries_historical_candidate_identity_through_publish() -> None:
    workflow = _release_workflow()
    jobs = workflow["jobs"]
    resolve = _job_step(jobs["resolve-candidate"], "Resolve exact tag target and latest exact-SHA main CI")["run"]
    candidate_evidence = _job_step(jobs["build-windows"], "Write candidate evidence")["run"]
    attest = _job_step(jobs["attest-evidence"], "Verify candidate binding and write trusted attestations")["run"]
    publish_verify = _job_step(jobs["publish-preflight"], "Re-resolve exact candidate, CI, and candidate artifact identities")["run"]
    publish = _job_step(jobs["publish-preflight"], "Fetch and verify candidate-bound evidence attestations")["run"]
    final = _job_step(jobs["final-publish"], "Verify the same candidate artifact, tag, and latest CI after approval")["run"]
    publication_evidence = _job_step(jobs["final-publish"], "Write publication evidence bound to the verified candidate")["run"]

    candidate_ref_guard = _throw_guard(resolve, "$env:GITHUB_REF")
    assert _guard_rejects(candidate_ref_guard, {"$env:GITHUB_REF": "refs/heads/untrusted"})
    assert "$candidateWorkflowSourceSha = $env:GITHUB_SHA.Trim().ToLowerInvariant()" in resolve
    assert "workflow_source_sha=$candidateWorkflowSourceSha" in resolve
    assert 'workflow_source_sha = "${{ needs.resolve-candidate.outputs.workflow_source_sha }}"' in candidate_evidence

    candidate_run_guard = _throw_guard(attest, "$candidateRun.name")
    assert "$candidateRun.head_sha -ne $candidateSha" not in candidate_run_guard
    assert "$candidateWorkflowSourceSha = $candidateRun.head_sha.Trim().ToLowerInvariant()" in attest
    candidate_binding_guard = _throw_guard(attest, "$candidatePayload.candidate.workflow_source_sha")
    assert _guard_rejects(
        candidate_binding_guard,
        {
            "$candidatePayload.schema_version": "1",
            "$candidatePayload.candidate.candidate_sha": "historical-candidate",
            "$candidatePayload.candidate.tag_target_sha": "historical-candidate",
            "$candidatePayload.candidate.candidate_run_id": "replacement-run",
            "$candidatePayload.candidate.observed_build_sha": "historical-candidate",
            "$candidatePayload.candidate.workflow_source_sha": "substituted-main-source",
            "$candidatePayload.package_artifact.id": "package-artifact",
            "$candidatePayload.package_artifact.checksum": "a" * 64,
            "$candidateSha": "historical-candidate",
            "$candidateRunId": "replacement-run",
            "$candidateWorkflowSourceSha": "trusted-later-main-source",
            "$package[0].id": "package-artifact",
        },
    )

    publish_candidate_guard = _throw_guard(publish_verify, "$candidateRun.name")
    assert "$candidateRun.head_sha -ne $candidateSha" not in publish_candidate_guard
    assert "$candidateWorkflowSourceSha = $candidateRun.head_sha.Trim().ToLowerInvariant()" in publish_verify
    assert "$candidatePayload.candidate.workflow_source_sha -ne $candidateWorkflowSourceSha" in publish
    assert "workflow_source_sha = $candidateWorkflowSourceSha" in publish
    assert "$verified.candidate.workflow_source_sha -ne $evidence.candidate.workflow_source_sha" in final
    assert "candidate_workflow_source_sha = $verified.candidate.workflow_source_sha" in publication_evidence


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
    for relative_path in (
        ".github/workflows/release-desktop.yml",
        ".github/workflows/ci.yml",
        ".github/workflows/pr-issue-guardrails.yml",
    ):
        workflow = yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))
        jobs = workflow["jobs"]
        uses = [
            step["uses"]
            for job in jobs.values()
            for step in job.get("steps", [])
            if "uses" in step
        ]
        assert uses, relative_path
        assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", action) for action in uses), relative_path


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


def _run_pr_guardrail_script(body: str, issues: dict[int, dict[str, object]]) -> dict[str, object]:
    node = shutil.which("node")
    assert node is not None, "node is required to validate pr-issue-guardrails.yml"
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/pr-issue-guardrails.yml").read_text(encoding="utf-8")
    )
    script = workflow["jobs"]["validate-pr-issue-contract"]["steps"][0]["with"]["script"]
    runner = (
        "const payload = JSON.parse(process.argv[1]);\n"
        "const failed = [];\n"
        "const info = [];\n"
        "const lookups = [];\n"
        "const core = { setFailed: (m) => failed.push(m), info: (m) => info.push(m) };\n"
        "const context = { repo: { owner: 'o', repo: 'r' }, payload: { pull_request: { body: payload.body } } };\n"
        "const github = { rest: { issues: { get: async ({ issue_number }) => {\n"
        "  lookups.push(issue_number);\n"
        "  const item = payload.issues[String(issue_number)];\n"
        "  if (!item) { const e = new Error('Not Found'); e.status = 404; throw e; }\n"
        "  return { data: item };\n"
        "} } } };\n"
        "(async () => {\n"
        "  await (async () => {\n"
        f"{script}\n"
        "  })();\n"
        "  console.log(JSON.stringify({ failed, info, lookups }));\n"
        "})().catch((err) => { console.error(err); process.exit(1); });\n"
    )
    proc = subprocess.run(
        [node, "-e", runner, json.dumps({"body": body, "issues": issues})],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def test_pr_issue_guardrails_validates_closing_and_linked_references() -> None:
    issues = {
        10: {"labels": [{"name": "enhancement"}, {"name": "ships:none"}]},
        11: {"labels": [{"name": "goal"}]},
        12: {"labels": [], "pull_request": {"url": "https://example.invalid/pr/12"}},
    }
    doc_section = "\n\n## Documentation impact\n\n- None: internal test."

    assert _run_pr_guardrail_script("No reference" + doc_section, issues)["failed"]
    assert not _run_pr_guardrail_script("Closes #10" + doc_section, issues)["failed"]
    assert not _run_pr_guardrail_script("Closes #10\nRefs #11" + doc_section, issues)["failed"]
    assert not _run_pr_guardrail_script("Closes #10\nPart of #11" + doc_section, issues)["failed"]

    missing_doc = _run_pr_guardrail_script("Closes #10", issues)
    assert any("Documentation impact" in msg for msg in missing_doc["failed"])

    comment_only_doc = _run_pr_guardrail_script(
        "Closes #10\n\n## Documentation impact\n\n<!-- placeholder only -->\n\n## Test plan\n- ok",
        issues,
    )
    assert any("Documentation impact" in msg for msg in comment_only_doc["failed"])

    closing_goal = _run_pr_guardrail_script("Closes #11" + doc_section, issues)
    assert any("goal" in msg for msg in closing_goal["failed"])

    closing_pr = _run_pr_guardrail_script("Closes #12" + doc_section, issues)
    assert any("pull request" in msg for msg in closing_pr["failed"])

    missing_ref = _run_pr_guardrail_script("Refs #999" + doc_section, issues)
    assert any("#999 was not found" in msg for msg in missing_ref["failed"])

    pr_ref = _run_pr_guardrail_script("Refs #12" + doc_section, issues)
    assert any("pull request" in msg for msg in pr_ref["failed"])

    dedup = _run_pr_guardrail_script("Closes #10\nRefs #10" + doc_section, issues)
    assert not dedup["failed"]
    assert dedup["lookups"] == [10]


def test_pr_issue_guardrails_resolves_shipping_class_from_closed_issues() -> None:
    def issue(*labels: str) -> dict[str, object]:
        return {"labels": [{"name": name} for name in labels]}

    issues = {
        20: issue("enhancement", "ships:none"),
        21: issue("enhancement", "ships:pre"),
        22: issue("enhancement", "ships:release"),
        23: issue("bug", "ships:hotfix"),
        24: issue("enhancement"),
        25: {"labels": ["ships:pre"]},  # API may return plain label strings
        30: issue("goal", "ships:release"),
    }
    doc_section = "\n\n## Documentation impact\n\n- None: internal test."

    def resolved(body: str) -> str:
        result = _run_pr_guardrail_script(body + doc_section, issues)
        assert not result["failed"], result["failed"]
        line = next(msg for msg in result["info"] if "Shipping class" in msg)
        return line.split("Shipping class: ", 1)[1].split(" ", 1)[0]

    assert resolved("Closes #20") == "none"
    assert resolved("Closes #25") == "pre"
    assert resolved("Closes #20\nCloses #21") == "pre"
    assert resolved("Closes #21\nFixes #22") == "release"
    assert resolved("Closes #22\nResolves #23\nCloses #20") == "hotfix"
    # An unclassified closed issue does not fail when another closed issue has a class.
    assert resolved("Closes #24\nCloses #21") == "pre"
    # Goals referenced with Refs are never counted, even when labelled.
    assert resolved("Closes #20\nRefs #30") == "none"

    for body in ("Closes #24", "Refs #30", "Part of #20"):
        failed = _run_pr_guardrail_script(body + doc_section, issues)["failed"]
        assert any("ships:none" in msg and "ships:hotfix" in msg for msg in failed), (body, failed)


def test_canonical_docs_have_no_broken_local_links() -> None:
    excluded_dirs = {"archive", "vendor", "releases", "superpowers"}
    md_files = [ROOT / "AGENTS.md", ROOT / "README.md"]
    for path in sorted((ROOT / "docs").rglob("*.md")):
        if path.relative_to(ROOT / "docs").parts[0] not in excluded_dirs:
            md_files.append(path)

    link_re = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    broken: list[str] = []
    for md in md_files:
        in_fence = False
        for lineno, line in enumerate(md.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for match in link_re.finditer(line):
                raw = match.group(1).strip()
                if not raw or raw.startswith(("http://", "https://", "mailto:", "#", "mdc:")):
                    continue
                target = unquote(raw.split("#", 1)[0].split("?", 1)[0]).strip()
                if target and not (md.parent / target).resolve().exists():
                    broken.append(f"{md.relative_to(ROOT)}:{lineno} -> {raw}")

    assert not broken, "Broken local links in canonical docs:\n" + "\n".join(broken)


def test_frontend_components_do_not_access_window_pywebview_directly() -> None:
    src_root = ROOT / "apps/desktop-web/src"
    bridge_root = src_root / "lib/bridge"
    pattern = re.compile(r"\b(?:window|globalThis)\s*\??\.\s*pywebview\b")
    violations: list[str] = []
    for path in sorted(src_root.rglob("*")):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        if path.name.endswith((".test.ts", ".test.tsx")):
            continue
        if bridge_root in path.parents:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith(("//", "*")):
                continue
            if pattern.search(line):
                violations.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")

    assert not violations, "Frontend code outside lib/bridge/ must use adapter.ts:\n" + "\n".join(violations)


def test_issue_templates_apply_needs_triage_label() -> None:
    for relative_path in (
        ".github/ISSUE_TEMPLATE/bug.yml",
        ".github/ISSUE_TEMPLATE/task.yml",
        ".github/ISSUE_TEMPLATE/goal.yml",
    ):
        template = yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))
        assert "needs-triage" in (template.get("labels") or []), relative_path


def test_task_and_bug_templates_ask_for_shipping_class() -> None:
    expected = {"none", "pre", "release", "hotfix"}
    for relative_path in (".github/ISSUE_TEMPLATE/bug.yml", ".github/ISSUE_TEMPLATE/task.yml"):
        template = yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))
        fields = [item for item in template["body"] if item.get("id") == "shipping_class"]
        assert len(fields) == 1, relative_path
        assert fields[0]["type"] == "dropdown", relative_path
        options = " ".join(fields[0]["attributes"]["options"])
        assert all(f"ships:{name}" in options for name in expected), relative_path


def test_pr_template_and_review_step_name_unreachable_unfinished_parts() -> None:
    template = (ROOT / ".github/PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")
    assert "unreachable" in template.lower()
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "unreachable" in agents.lower()
    for name in ("ships:none", "ships:pre", "ships:release", "ships:hotfix"):
        assert name in agents
        assert name in (ROOT / "docs/agents/triage-labels.md").read_text(encoding="utf-8")


def test_agent_ignore_and_context_configs_exclude_high_noise_roots() -> None:
    claudeignore = {
        line.strip()
        for line in (ROOT / ".claudeignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    geminiignore = {
        line.strip()
        for line in (ROOT / ".geminiignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    context_prefs = json.loads(
        (ROOT / ".claude/agent-context-preferences.json").read_text(encoding="utf-8")
    )
    excluded = set(context_prefs.get("exclude_from_context") or [])

    for entry in (
        ".claude/worktrees/",
        "build/",
        "dist/",
        "data/dev-runtime/",
        "data/raw/",
        ".venv/",
        "node_modules/",
        ".pytest_cache/",
        "tmp/",
        "scratch/",
    ):
        assert entry in claudeignore, f"missing from .claudeignore: {entry}"

    for entry in (
        ".claude/",
        "build/",
        "dist/",
        "data/",
        ".venv/",
        "node_modules/",
        ".pytest_cache/",
        "tmp/",
        "scratch/",
    ):
        assert entry in geminiignore, f"missing from .geminiignore: {entry}"

    for entry in (
        ".claude/worktrees/",
        "build/",
        "dist/",
        "data/dev-runtime/",
        "data/raw/",
        "node_modules/",
        ".pytest_cache/",
        "tmp/",
        "scratch/",
    ):
        assert entry in excluded, f"missing from agent-context-preferences.json: {entry}"
