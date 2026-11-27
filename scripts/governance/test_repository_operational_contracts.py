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
    workflow["on"] = workflow.pop("on", None) or workflow.pop(True)
    return workflow


def _run_source(job: dict[str, object]) -> str:
    return "\n".join(str(step.get("run", "")) for step in job.get("steps", []))


PUBLISH_JOBS = ("publish-automatic", "publish-approved", "rehearse-publication")


def test_release_workflow_runs_after_green_main_ci_and_offers_a_dry_run() -> None:
    workflow = _release_workflow()
    triggers = workflow["on"]

    assert set(triggers) == {"workflow_run", "workflow_dispatch"}
    assert triggers["workflow_run"] == {"workflows": ["CI"], "types": ["completed"], "branches": ["main"]}
    inputs = triggers["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"dry_run", "assume_class"}
    assert inputs["dry_run"]["type"] == "boolean" and inputs["dry_run"]["default"] is True
    decide_if = workflow["jobs"]["decide"]["if"]
    for condition in (
        "github.event.workflow_run.conclusion == 'success'",
        "github.event.workflow_run.event == 'push'",
        "github.event.workflow_run.head_branch == 'main'",
    ):
        assert condition in decide_if


def test_release_workflow_asks_the_decision_module_before_building() -> None:
    jobs = _release_workflow()["jobs"]
    decide = _run_source(jobs["decide"])

    assert "scripts/release/publication_workflow.py facts" in decide
    assert "scripts/release/publication_decision.py decide" in decide
    assert "scripts/release/publication_workflow.py report" in decide
    assert jobs["build"]["needs"] == "decide"
    assert jobs["build"]["if"] == "needs.decide.outputs.publish == 'true'"
    assert jobs["build"]["steps"][0]["with"]["ref"] == "${{ needs.decide.outputs.candidate_sha }}"


def test_release_workflow_builds_once_with_the_decided_version_and_never_rebuilds() -> None:
    jobs = _release_workflow()["jobs"]
    build = _run_source(jobs["build"])

    assert set(jobs) == {"decide", "build", *PUBLISH_JOBS}
    assert ".\\desktop\\build_desktop.ps1 -Version $env:RELEASE_VERSION" in build
    assert jobs["build"]["env"]["RELEASE_VERSION"] == "${{ needs.decide.outputs.version }}"
    assert "CVMAnalytics-windows-v$env:RELEASE_VERSION.zip" in build
    assert "$roots -contains 'CVMAnalytics.exe' -and $roots -contains '_internal'" in build
    assert '"/DAppVersion=$env:RELEASE_VERSION"' in build and "desktop\\installer.iss" in build
    assert build.index("build_desktop.ps1") < build.index("Compress-Archive") < build.index("installer.iss")
    for name, job in jobs.items():
        if name != "build":
            for builder in ("build_desktop.ps1", "Compress-Archive", "installer.iss", "ISCC"):
                assert builder not in str(job), (name, builder)
        assert "git commit" not in str(job) and "git push" not in str(job), name
        assert "softprops/action-gh-release" not in str(job), name


def test_release_workflow_publishes_the_built_candidate_with_one_shared_step_list() -> None:
    jobs = _release_workflow()["jobs"]
    steps = jobs["publish-automatic"]["steps"]

    for name in PUBLISH_JOBS:
        assert jobs[name]["steps"] == steps, name
        assert jobs[name]["needs"] == ["decide", "build"], name
        assert jobs[name]["env"]["EXPECTED_SHA256"] == "${{ needs.build.outputs.zip_sha256 }}", name
        assert jobs[name]["env"]["EXPECTED_SETUP_SHA256"] == "${{ needs.build.outputs.setup_sha256 }}", name
    downloads = [step["with"] for step in steps if step.get("uses", "").startswith("actions/download-artifact@")]
    # Same run only (no run-id), so no older or foreign artifact can be substituted.
    assert downloads == [
        {"name": "publication-decision", "path": "decision"},
        {"name": "publication-candidate", "path": "candidate"},
    ]
    publish = _run_source(jobs["publish-automatic"])
    assert "publication_workflow.py publish" in publish
    assert '--expected-sha256 "$EXPECTED_SHA256"' in publish
    assert '--expected-setup-sha256 "$EXPECTED_SETUP_SHA256"' in publish


def test_release_workflow_keeps_the_smoke_tested_installer_in_the_candidate() -> None:
    build = _release_workflow()["jobs"]["build"]
    steps = {step.get("id"): step for step in build["steps"]}

    assert build["outputs"]["setup_sha256"] == "${{ steps.installer.outputs.setup_sha256 }}"
    assert "setup_sha256=$hash" in steps["installer"]["run"]
    smoke = _run_source(build)
    for check in ("/VERYSILENT", "unins000.exe", "Documents\\CVMAnalytics", "Uninstall left $dir behind."):
        assert check in smoke, check
    upload = next(step for step in build["steps"] if step.get("uses", "").startswith("actions/upload-artifact@"))
    assert upload["with"]["name"] == "publication-candidate"
    assert upload["with"]["path"].splitlines() == [
        f"CVMAnalytics-{name}-v${{{{ needs.decide.outputs.version }}}}.{ext}"
        for name, extensions in (("windows", ("zip", "zip.sha256")), ("Setup", ("exe", "exe.sha256")))
        for ext in extensions
    ]


def test_installer_is_per_user_and_its_uninstaller_never_touches_user_data() -> None:
    script = (ROOT / "desktop/installer.iss").read_text(encoding="utf-8")
    directives = dict(
        line.split("=", 1) for line in script.splitlines() if re.match(r"^[A-Za-z]+=", line)
    )

    assert directives["PrivilegesRequired"] == "lowest"
    assert "PrivilegesRequiredOverridesAllowed" not in directives  # never an elevated all-users install
    assert directives["DefaultDirName"] == "{localappdata}\\Programs\\CVMAnalytics"
    assert directives["AppVersion"] == "{#AppVersion}"
    assert directives["OutputBaseFilename"] == "CVMAnalytics-Setup-v{#AppVersion}"
    assert re.search(r'^Source: "\.\.\\dist\\CVMAnalytics\\\*"; DestDir: "\{app\}"', script, re.M)
    assert re.search(r'^Name: "\{autoprograms\}\\CVM Analytics"', script, re.M)
    assert re.search(r'^Name: "desktopicon";.*Flags: unchecked$', script, re.M)
    # Deletions are limited to the two bundle entries the updater swaps, inside {app}.
    deletions = re.findall(r'^Type: \w+; Name: "([^"]+)"', script, re.M)
    assert set(deletions) == {"{app}\\_internal", "{app}\\CVMAnalytics.exe"}
    lowered = "\n".join(line for line in script.lower().splitlines() if not line.startswith(";"))
    for user_data in ("{userdocs}", "{commondocs}", "documents\\cvmanalytics", "{localappdata}\\cvmanalytics"):
        assert user_data not in lowered, user_data


def test_release_workflow_keeps_write_access_on_the_publish_jobs_and_approval_in_release_publication() -> None:
    workflow = _release_workflow()
    jobs = workflow["jobs"]

    assert workflow["permissions"] == {"contents": "read"}
    writers = {name for name, job in jobs.items() if job.get("permissions", {}).get("contents") == "write"}
    assert writers == {"publish-automatic", "publish-approved"}
    assert {name for name, job in jobs.items() if "environment" in job} == {"publish-approved"}
    assert jobs["publish-approved"]["environment"] == "release-publication"
    assert jobs["publish-approved"]["if"] == (
        "needs.decide.outputs.dry_run == 'false' && needs.decide.outputs.approval_required == 'true'"
    )
    assert jobs["publish-automatic"]["if"] == (
        "needs.decide.outputs.dry_run == 'false' && needs.decide.outputs.approval_required == 'false'"
    )
    assert jobs["rehearse-publication"]["if"] == "needs.decide.outputs.dry_run == 'true'"
    assert jobs["rehearse-publication"]["permissions"] == {"contents": "read"}
    assert "${{ needs.decide.outputs.version }}" in jobs["publish-approved"]["name"]
    assert "${{ needs.decide.outputs.kind }}" in jobs["publish-approved"]["name"]


def test_release_workflow_collapses_and_supersedes_runs_with_one_cancelling_group() -> None:
    concurrency = _release_workflow()["concurrency"]

    assert concurrency["cancel-in-progress"] is True
    assert "&& 'release-publication'" in concurrency["group"]
    assert "format('release-publication-noop-{0}', github.run_id)" in concurrency["group"]
    assert "!inputs.dry_run" in concurrency["group"]


def test_release_workflow_transports_dispatch_values_as_environment_data_not_shell_code() -> None:
    jobs = _release_workflow()["jobs"]

    assert all("${{" not in _run_source(job) for job in jobs.values())
    decide_env = next(step["env"] for step in jobs["decide"]["steps"] if step.get("id") == "decide")
    assert decide_env["ASSUME_CLASS"] == "${{ inputs.assume_class }}"


def test_release_docs_describe_build_once_publication_not_the_retired_gate() -> None:
    for relative_path in ("docs/release-process.md", "docs/build-release.md"):
        document = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "release-publication" in document, relative_path
        assert "publication_decision.py" in document, relative_path
        for retired in ("attest", "candidate_run_id", "#440"):
            assert retired not in document, (relative_path, retired)
    release_process = (ROOT / "docs/release-process.md").read_text(encoding="utf-8")
    assert "pending_deployments" in release_process
    assert "explicit" in release_process


def test_candidate_test_command_verifies_before_launch_and_is_documented() -> None:
    script = (ROOT / "scripts/release/open-candidate.ps1").read_text(encoding="utf-8")
    uploads = {
        step["with"]["name"]
        for job in _release_workflow()["jobs"].values()
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    }

    # The script reads the artifacts the release workflow actually uploads.
    assert {"publication-candidate", "publication-decision"} <= uploads
    assert '"publication-candidate", "publication-decision"' in script
    assert "name=publication-candidate" in script  # how "latest" is resolved
    assert "Refusing to open this candidate" in script
    assert "Get-Process -Name CVMAnalytics" in script
    assert "CVMAnalytics-candidates" in script
    # Nothing is extracted or launched before the checksum matches.
    assert script.index("Get-FileHash") < script.index("Expand-Archive") < script.index("Start-Process")
    release_process = (ROOT / "docs/release-process.md").read_text(encoding="utf-8")
    assert "## Testing a candidate" in release_process
    assert "scripts/release/open-candidate.ps1" in release_process


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
