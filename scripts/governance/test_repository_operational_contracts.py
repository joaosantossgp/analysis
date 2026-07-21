from __future__ import annotations

import importlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_seed_catalog_smoke_uses_resolvable_platform_modules() -> None:
    workflow = (ROOT / ".github/workflows/seed_catalog.yml").read_text(
        encoding="utf-8"
    )
    expected_imports = {
        "from src.platform.db import build_engine": ("src.platform.db", "build_engine"),
        "from src.platform.settings import build_settings": (
            "src.platform.settings",
            "build_settings",
        ),
    }

    violations = []
    for stale in (
        "from src.db import build_engine",
        "from src.settings import build_settings",
    ):
        if stale in workflow:
            violations.append(f"stale seed import: {stale}")
    for statement, (module_name, symbol_name) in expected_imports.items():
        if statement not in workflow:
            violations.append(f"missing active seed import: {statement}")
    assert not violations, "\n".join(violations)
    for statement, (module_name, symbol_name) in expected_imports.items():
        symbol = getattr(importlib.import_module(module_name), symbol_name)
        assert callable(symbol)


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
        "desktop/bridge_api/**",
    }

    violations = [f"stale path-policy entry: {path}" for path in sorted(patterns & stale)]
    violations.extend(
        f"missing active path-policy entry: {path}" for path in sorted(required - patterns)
    )
    assert not violations, "\n".join(violations)
    for relative_path in required:
        if "*" not in relative_path:
            assert (ROOT / relative_path).is_file()


def test_worktree_lifecycle_scripts_default_to_main() -> None:
    for relative_path in (
        "scripts/governance/worktree_create.ps1",
        "scripts/governance/worktree_remove.ps1",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8-sig")
        match = re.search(r'\[string\]\$Base\s*=\s*"([^"]+)"', source)
        assert match is not None, relative_path
        assert match.group(1) == "main", relative_path
