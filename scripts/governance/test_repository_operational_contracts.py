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


def test_release_workflow_requires_exact_sha_candidate_and_protected_publish_gate() -> None:
    workflow = (ROOT / ".github/workflows/release-desktop.yml").read_text(
        encoding="utf-8"
    )

    required_fragments = (
        "workflow_dispatch:",
        "phase:",
        "candidate_sha:",
        "candidate_run_id:",
        "resolve-candidate:",
        "build-windows:",
        "publish-preflight:",
        "final-publish:",
        "event=push&branch=main&head_sha=$candidateSha",
        "actions/upload-artifact@v4",
        "actions/download-artifact@v4",
        "release-publication",
        "contents: write",
        "candidate-evidence.json",
        "manual-evidence.json",
        "softprops/action-gh-release@v2",
    )
    missing = [fragment for fragment in required_fragments if fragment not in workflow]

    assert not missing, f"release evidence gate missing: {', '.join(missing)}"
    assert "push:\n    tags:" not in workflow
    assert workflow.count("contents: write") == 1
