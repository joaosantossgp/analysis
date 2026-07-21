# Architecture & Product Hardening Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver six bounded architecture/product hardening children that repair proven guardrail drift, expose existing tests in CI, protect BridgeApi declarations, characterize gated startup/release risks, and validate a disposable current-head package without changing product behavior.

**Architecture:** Preserve the active Vite -> pywebview -> Python -> local-store architecture. Add test-first static guardrails at the repository and TypeScript boundaries, keep the two behavior-sensitive findings as investigation-only issues, and finish with isolated package evidence. Each implementation child owns a separate worktree, branch, review, and PR.

**Tech Stack:** Python 3.11, pytest, TypeScript 5.6, Vitest 4, Vite 6, GitHub Actions YAML, PowerShell 7, PyInstaller/pywebview, SQLite, GitHub Issues/PRs.

## Global Constraints

- Changing or removing the automatic startup metadata refresh requires explicit approval.
- Modifying release-publication behavior requires explicit approval.
- Any database, public contract, financial-calculation, updater-channel, destructive, architectural, or user-visible behavior change requires explicit approval.
- Preserve product behavior, local-first/offline reads, downloaded user data, source snapshots and lineage, active routes/workflows, bridge compatibility, Excel behavior, build/packaging/updater behavior, and existing performance unless a measured improvement is delivered.
- Do not add a dependency, code generator, schema framework, broad rewrite, feature, stable release, or broad `desktop/services.py` extraction.
- BridgeApi work starts and ends with duplicate removal, a static duplicate-name test, a verified Python-versus-TypeScript inventory, and mismatch documentation unless evidence triggers a separately approved scope.
- Every claimed baseline records source commit SHA, exact command, environment, UTC timestamp, duration, pass/fail result, and log/artifact location when available.
- Work from clean `origin/main` in a child-specific isolated worktree; never write through the dirty primary checkout.
- Use test-first red/green cycles for every implementation change and independent specification-plus-quality review before merge.
- Never run the seed workflow against a remote database during this wave.
- Never publish a tag, GitHub release, stable build, or updater channel change.

---

## Tracking setup

After this plan passes self-review, the controller creates exactly one Epic and
six child issues. The created issue URL is the source of the numeric issue id;
the controller records each child in the Epic checklist and each child records
the Epic as its parent in the body.

**Epic title:** `[Epic] Architecture & Product Hardening Wave`

**Children:**

1. `[Ops] Repair stale repository operational contracts`
2. `[CI] Run Vite tests in the desktop frontend job`
3. `[Bridge] Guard BridgeApi declaration integrity`
4. `[Investigation] Characterize automatic startup metadata refresh`
5. `[Investigation] Define release-publication evidence gate`
6. `[Validation] Verify a current-head packaged desktop candidate`

Every issue body includes objective, evidence with source commit
`9ecd2db246668452262624ea7ad4f370eb7a67d9`, scope, non-goals, risk, lane,
expected write set, dependencies, acceptance criteria, exact validation
commands, provenance requirements, and approval boundary. Before creation,
search all open and closed issues/PRs by each title's distinctive terms and
record overlap decisions for #134, #239, #369, #372, #374, #380, #382, #383,
#385, and #397.

The planning branch contains the approved design commit before tracking setup:

```text
1b9e9fb docs: record architecture hardening wave design
```

Immediately after this plan is committed, record its exact SHA with
`git rev-parse HEAD` in the Epic and planning PR.

After issue creation, push the planning branch and open one docs-only PR linked
to the Epic. Review and merge it before implementation children merge so task
briefs can link the canonical design and plan on `main`.

---

### Task 1: Repair repository operational-contract drift

**Issue title:** `[Ops] Repair stale repository operational contracts`

**Files:**
- Create: `scripts/governance/test_repository_operational_contracts.py`
- Modify: `.github/workflows/seed_catalog.yml:49-50`
- Modify: `.github/guardrails/path-policy.json:96-107`
- Modify: `scripts/governance/worktree_remove.ps1:12`

**Interfaces:**
- Consumes: active modules `src.platform.db.build_engine` and `src.platform.settings.build_settings`; policy matcher implemented in `.github/workflows/pr-issue-guardrails.yml`; repository default branch `main`.
- Produces: a static pytest contract that proves the seed smoke imports resolvable active modules, the critical-runtime group names active paths, and both worktree lifecycle scripts default to `main`.

- [ ] **Step 1: Create the issue worktree from clean main**

Run from the primary repository after the issue number is recorded:

```powershell
.\scripts\governance\worktree_create.ps1 `
  -Issue $issueNumber `
  -Slug repository-operational-contracts `
  -Lane ops-quality `
  -Base main
```

Then bootstrap in the created worktree:

```powershell
.\scripts\setup\bootstrap_worktree.ps1
git rev-parse HEAD
git status --short
```

Expected: the source SHA equals current clean `main`, bootstrap passes, and
status is empty. Record command provenance in ignored
`scratch/architecture-hardening-wave/task-1/`.

- [ ] **Step 2: Write the failing operational-contract tests**

Create `scripts/governance/test_repository_operational_contracts.py`:

```python
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

    assert "from src.db import build_engine" not in workflow
    assert "from src.settings import build_settings" not in workflow
    for statement, (module_name, symbol_name) in expected_imports.items():
        assert statement in workflow
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

    assert patterns.isdisjoint(stale)
    assert required <= patterns
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
```

- [ ] **Step 3: Run the tests and verify the expected red state**

Run:

```powershell
python -m pytest scripts/governance/test_repository_operational_contracts.py -q
```

Expected: failures identify the two stale seed imports, the removed path-policy
entries, and `worktree_remove.ps1` defaulting to `master`. A collection/import
error is not an acceptable red state.

- [ ] **Step 4: Apply the minimal operational repairs**

In `.github/workflows/seed_catalog.yml`, use only:

```python
from src.platform.db import build_engine
from src.platform.settings import build_settings
```

In `.github/guardrails/path-policy.json`, replace the seven removed `src/*`
entries with the active required set from the test. Preserve all other group
properties and all other policy groups.

In `scripts/governance/worktree_remove.ps1`, change only:

```powershell
[string]$Base = "main",
```

- [ ] **Step 5: Run the targeted tests and verify green**

Run:

```powershell
python -m pytest scripts/governance/test_repository_operational_contracts.py -q
```

Expected: 3 passed.

- [ ] **Step 6: Run focused compatibility validation**

Run:

```powershell
python -m pytest tests/test_settings.py tests/test_desktop_runtime_paths.py -q
python -m pytest tests -q
git diff --check
```

Expected: all commands pass. Do not dispatch or run the remote seed workflow.
Record the exact counts and provenance in the issue/PR.

- [ ] **Step 7: Commit, review, push, and open the focused PR**

```powershell
git add -- .github/workflows/seed_catalog.yml .github/guardrails/path-policy.json scripts/governance/worktree_remove.ps1 scripts/governance/test_repository_operational_contracts.py
git diff --cached --check
git commit -m "fix(ops): align repository operational contracts"
```

Generate the task review package from the recorded task base, obtain both
specification-compliance and code-quality approval, push the task branch, open a
PR that closes the child issue, and wait for required checks. Merge only after
review is clean and checks pass.

---

### Task 2: Run Vite tests in the desktop frontend CI job

**Issue title:** `[CI] Run Vite tests in the desktop frontend job`

**Files:**
- Create: `scripts/governance/test_frontend_ci_contract.py`
- Modify: `.github/workflows/ci.yml:98-105`

**Interfaces:**
- Consumes: existing `apps/desktop-web/package.json` script `test = vitest run` and the existing Node 22/npm-ci frontend job.
- Produces: CI ordering `npm ci -> npm run test -> npm run typecheck -> npm run build` plus a static pytest regression check.

- [ ] **Step 1: Create and bootstrap the issue worktree**

Use `scripts/governance/worktree_create.ps1` with the recorded issue number,
slug `frontend-ci-vitest`, lane `ops-quality`, and base `main`. Run
`scripts/setup/bootstrap_worktree.ps1`, record the source SHA, and require a
clean status.

- [ ] **Step 2: Write the failing CI contract test**

Create `scripts/governance/test_frontend_ci_contract.py`:

```python
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_desktop_frontend_ci_runs_tests_before_typecheck_and_build() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    install = workflow.index("- name: Install Vite desktop UI dependencies")
    test = workflow.index("- name: Test Vite desktop UI")
    typecheck = workflow.index("- name: Typecheck Vite desktop UI")
    build = workflow.index("- name: Build Vite desktop UI")

    assert install < test < typecheck < build
    test_block = workflow[test:typecheck]
    assert "run: npm run test" in test_block
```

- [ ] **Step 3: Verify the test fails for the missing CI step**

```powershell
python -m pytest scripts/governance/test_frontend_ci_contract.py -q
```

Expected: one failure because `Test Vite desktop UI` is absent.

- [ ] **Step 4: Add the existing test command to CI**

Insert after `npm ci` and before typecheck:

```yaml
      - name: Test Vite desktop UI
        run: npm run test
```

Do not change Node version, caching, lockfiles, dependencies, triggers, Python
jobs, or build steps.

- [ ] **Step 5: Verify targeted and frontend green states**

```powershell
python -m pytest scripts/governance/test_frontend_ci_contract.py -q
npm --prefix apps/desktop-web run test
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
git diff --check
```

Expected: static test passes; clean-main frontend baseline is at least 14 files
and 75 tests; typecheck/build pass. Record actual counts and durations rather
than copying these expected lower bounds into evidence.

- [ ] **Step 6: Commit and complete the review/PR cycle**

```powershell
git add -- .github/workflows/ci.yml scripts/governance/test_frontend_ci_contract.py
git diff --cached --check
git commit -m "ci: run desktop Vite tests"
```

Obtain task specification and quality review, push, open a PR closing the child,
and merge only after required GitHub checks prove the new Vite test step ran.

---

### Task 3: Guard BridgeApi declaration integrity

**Issue title:** `[Bridge] Guard BridgeApi declaration integrity`

**Files:**
- Create: `apps/desktop-web/src/lib/bridge/types.contract.test.ts`
- Modify: `apps/desktop-web/src/lib/bridge/types.ts:1654-end-of-interface`
- Create: `scripts/diagnostics/bridge_method_inventory.py`
- Create: `tests/test_bridge_method_inventory.py`
- Create: `docs/reference/bridge-method-inventory.md`

**Interfaces:**
- Consumes: `BridgeApi` in `apps/desktop-web/src/lib/bridge/types.ts`; `CVMBridge` mixin imports/bases in `desktop/bridge.py`; public methods declared on the referenced mixin classes.
- Produces: unique TypeScript declaration names, pure-stdlib inventory function `build_inventory(root: Path) -> dict[str, object]`, JSON CLI output, and a committed mismatch report. It does not change a runtime method.

- [ ] **Step 1: Create and bootstrap the shared issue worktree**

This child spans the frontend declaration, Python inventory, tests, and docs,
so classify it `lane:master`. The governance helper does not accept that lane;
create the isolated worktree explicitly after validating the ignored target:

```powershell
$branch = "task/$issueNumber-bridge-api-integrity"
$path = Join-Path (git rev-parse --show-toplevel) ".claude/worktrees/master/$issueNumber-bridge-api-integrity"
git check-ignore .claude/worktrees
git worktree add $path -b $branch origin/main
Set-Location $path
.\scripts\setup\bootstrap_worktree.ps1
git rev-parse HEAD
git status --short
```

Expected: ignore verification and bootstrap pass, the source is current clean
`origin/main`, status is empty, and the canonical planning docs are present.

- [ ] **Step 2: Write the failing TypeScript duplicate-name test**

Create `apps/desktop-web/src/lib/bridge/types.contract.test.ts`:

```typescript
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

function bridgeApiMethodNames(source: string): string[] {
  const marker = "export interface BridgeApi {";
  const start = source.indexOf(marker);
  if (start < 0) throw new Error("BridgeApi interface marker not found");

  const names: string[] = [];
  for (const line of source.slice(start + marker.length).split(/\r?\n/)) {
    if (line === "}") break;
    const match = /^  ([A-Za-z_$][\w$]*)\s*\(/.exec(line);
    if (match) names.push(match[1]);
  }
  return names;
}

describe("BridgeApi declaration contract", () => {
  it("declares every method name exactly once", () => {
    const path = fileURLToPath(new URL("./types.ts", import.meta.url));
    const names = bridgeApiMethodNames(readFileSync(path, "utf8"));
    const counts = new Map<string, number>();
    for (const name of names) counts.set(name, (counts.get(name) ?? 0) + 1);

    const duplicates = [...counts]
      .filter(([, count]) => count > 1)
      .map(([name]) => name)
      .sort();
    expect(duplicates).toEqual([]);
  });
});
```

- [ ] **Step 3: Run the test and verify duplicate-name red output**

```powershell
npm --prefix apps/desktop-web run test -- src/lib/bridge/types.contract.test.ts
```

Expected: the assertion fails with a non-empty sorted duplicate-name list. A
missing-interface or TypeScript compilation error is not an acceptable red
state. Save the duplicate list as issue evidence.

- [ ] **Step 4: Remove only redundant declarations**

Delete the later repeated declarations from `BridgeApi`. Retain the first
declaration and its exact parameter/return type for every unique name. Do not
change declarations outside the duplicate set, split the interface, generate
code, or change Python/adapter/mock runtime behavior.

- [ ] **Step 5: Verify the duplicate guardrail is green**

```powershell
npm --prefix apps/desktop-web run test -- src/lib/bridge/types.contract.test.ts
npm --prefix apps/desktop-web run typecheck
```

Expected: targeted test and typecheck pass.

- [ ] **Step 6: Write the failing inventory-tool unit test**

Create `tests/test_bridge_method_inventory.py`:

```python
from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_build_inventory():
    module_path = ROOT / "scripts/diagnostics/bridge_method_inventory.py"
    assert module_path.is_file()
    spec = importlib.util.spec_from_file_location("bridge_method_inventory", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_inventory


def test_build_inventory_compares_cvmbridge_mixins_with_typescript(tmp_path: Path) -> None:
    (tmp_path / "desktop/bridge_api").mkdir(parents=True)
    (tmp_path / "apps/desktop-web/src/lib/bridge").mkdir(parents=True)
    (tmp_path / "desktop/bridge.py").write_text(
        "from desktop.bridge_api.alpha import AlphaMixin\n"
        "class CVMBridge(AlphaMixin):\n"
        "    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "desktop/bridge_api/alpha.py").write_text(
        "class AlphaMixin:\n"
        "    def ping(self, params=None):\n"
        "        return params\n"
        "    def _private(self):\n"
        "        return None\n",
        encoding="utf-8",
    )
    (tmp_path / "apps/desktop-web/src/lib/bridge/types.ts").write_text(
        "export interface BridgeApi {\n"
        "  ping(params?: Record<string, unknown>): Promise<unknown>;\n"
        "  typescript_only(params?: Record<string, unknown>): Promise<unknown>;\n"
        "  ping(params?: Record<string, unknown>): Promise<unknown>;\n"
        "}\n",
        encoding="utf-8",
    )

    inventory = _load_build_inventory()(tmp_path)

    assert inventory["python_methods"] == ["ping"]
    assert inventory["typescript_methods"] == ["ping", "typescript_only"]
    assert inventory["typescript_duplicates"] == ["ping"]
    assert inventory["python_only"] == []
    assert inventory["typescript_only"] == ["typescript_only"]
```

- [ ] **Step 7: Verify the inventory test fails because the tool is absent**

```powershell
python -m pytest tests/test_bridge_method_inventory.py -q
```

Expected: the test fails at `assert module_path.is_file()` because the inventory
tool does not yet exist. A collection/import error is not an acceptable red
state.

- [ ] **Step 8: Implement the pure-stdlib inventory tool**

Create `scripts/diagnostics/bridge_method_inventory.py` with these exact public
interfaces:

```python
from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _typescript_method_names(path: Path) -> tuple[list[str], list[str]]:
    source = path.read_text(encoding="utf-8")
    marker = "export interface BridgeApi {"
    start = source.find(marker)
    if start < 0:
        raise ValueError("BridgeApi interface marker not found")

    names: list[str] = []
    for line in source[start + len(marker) :].splitlines():
        if line == "}":
            break
        stripped = line.lstrip()
        if len(line) - len(stripped) != 2 or "(" not in stripped:
            continue
        candidate = stripped.split("(", 1)[0].strip()
        if candidate.isidentifier():
            names.append(candidate)

    counts = Counter(names)
    return sorted(counts), sorted(name for name, count in counts.items() if count > 1)


def _bridge_mixin_targets(root: Path) -> list[tuple[Path, str]]:
    bridge_path = root / "desktop/bridge.py"
    tree = ast.parse(bridge_path.read_text(encoding="utf-8"), filename=str(bridge_path))
    imports: dict[str, tuple[Path, str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        module_path = root / (node.module.replace(".", "/") + ".py")
        for alias in node.names:
            imports[alias.asname or alias.name] = (module_path, alias.name)

    bridge_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CVMBridge"
    )
    targets: list[tuple[Path, str]] = []
    for base in bridge_class.bases:
        if not isinstance(base, ast.Name) or base.id not in imports:
            raise ValueError(f"Unresolved CVMBridge base: {ast.unparse(base)}")
        targets.append(imports[base.id])
    return targets


def _python_method_names(root: Path) -> list[str]:
    methods: set[str] = set()
    for module_path, class_name in _bridge_mixin_targets(root):
        tree = ast.parse(
            module_path.read_text(encoding="utf-8"), filename=str(module_path)
        )
        mixin = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
        for node in mixin.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    methods.add(node.name)
    return sorted(methods)


def build_inventory(root: Path) -> dict[str, Any]:
    python_methods = _python_method_names(root)
    typescript_methods, duplicates = _typescript_method_names(
        root / "apps/desktop-web/src/lib/bridge/types.ts"
    )
    python_set = set(python_methods)
    typescript_set = set(typescript_methods)
    return {
        "python_methods": python_methods,
        "typescript_methods": typescript_methods,
        "typescript_duplicates": duplicates,
        "python_only": sorted(python_set - typescript_set),
        "typescript_only": sorted(typescript_set - python_set),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(build_inventory(args.root.resolve()), indent=2))


if __name__ == "__main__":
    main()
```

The implementation is a diagnostic inventory, not code generation. Do not add
dependencies or use the output to mutate source files.

- [ ] **Step 9: Verify the inventory unit test is green**

```powershell
python -m pytest tests/test_bridge_method_inventory.py -q
```

Expected: 1 passed.

- [ ] **Step 10: Generate and inspect the real inventory**

```powershell
New-Item -ItemType Directory -Force scratch\architecture-hardening-wave\task-3 | Out-Null
python scripts/diagnostics/bridge_method_inventory.py --root . |
  Tee-Object scratch\architecture-hardening-wave\task-3\bridge-method-inventory.json
```

Expected: `typescript_duplicates` is empty after Step 4. Record the full sorted
Python/TypeScript method lists and both mismatch lists. Compare every mismatch
to active TypeScript call sites (`callBridge`) and Python tests before assigning
one of: intentionally Python-only legacy method, active Python-only method,
TypeScript-only declaration, or needs separately approved follow-up.

- [ ] **Step 11: Document the verified inventory and mismatches**

Create `docs/reference/bridge-method-inventory.md` with the exact title
`Desktop Bridge Method Inventory`. Populate its provenance block from the
captured command metadata: source SHA, the literal command
`python scripts/diagnostics/bridge_method_inventory.py --root .`, complete
Windows/PowerShell/Python/Node environment, ISO-8601 UTC timestamp, duration,
PASS/FAIL, and ignored JSON artifact path.

Add these exact sections: `Inventory summary`, `Python-only methods`,
`TypeScript-only methods`, `Duplicate declarations`, and `Decision`. The
summary table records actual unique counts. The mismatch sections list every
actual sorted name with its source/call-site classification. The duplicate
section states `None` only if the generated JSON proves an empty list. The
decision states that no runtime method was added, removed, renamed, generated,
or changed and that any contract follow-up requires a separately scoped issue
and applicable approval. Empty fields, guessed values, and template markers
make this step fail.

- [ ] **Step 12: Run the complete relevant validation**

```powershell
npm --prefix apps/desktop-web run test
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
python -m pytest tests/test_bridge_method_inventory.py -q
python -m pytest tests -q
git diff --check
```

Expected: all pass. Compare test counts to the recorded source SHA and explain
the new tests; do not copy earlier counts as current evidence.

- [ ] **Step 13: Commit and complete the review/PR cycle**

```powershell
git add -- apps/desktop-web/src/lib/bridge/types.contract.test.ts apps/desktop-web/src/lib/bridge/types.ts scripts/diagnostics/bridge_method_inventory.py tests/test_bridge_method_inventory.py docs/reference/bridge-method-inventory.md
git diff --cached --check
git commit -m "test(bridge): guard BridgeApi method integrity"
```

Task review must explicitly verify that the unique TypeScript method set is
unchanged, mismatch documentation matches the generated artifact, and no
runtime/public contract changed. Push/open/merge the focused PR only after
review and required checks are clean.

---

### Task 4: Characterize the automatic startup metadata refresh

**Issue title:** `[Investigation] Characterize automatic startup metadata refresh`

**Files:**
- Inspect: `desktop/app.py:98-162,1002-1118,1121-1232`
- Inspect: `tests/test_metadata_fixes.py:380-542`
- Inspect: `tests/test_desktop_runtime_paths.py`
- Inspect: `src/companies/catalog.py`
- Inspect: active CNPJ consumers in `src/financials`, `src/companies`, `desktop/bridge_api`, and `apps/desktop-web`
- Update: GitHub child issue body/comments only

**Interfaces:**
- Consumes: the current startup thread, data-root resolution, lock status, direct SQLite writes, catalog network client, stdout behavior, and active CNPJ consumers.
- Produces: an independently reviewed evidence record and decision options. It produces no code or behavior change.

- [ ] **Step 1: Reproduce path selection without network or user-data writes**

Use pytest monkeypatch/temporary directories or direct calls to path resolver
functions only. Run the existing focused tests:

```powershell
python -m pytest tests/test_desktop_runtime_paths.py tests/test_metadata_fixes.py -q
```

Do not invoke `_background_remote_metadata_refresh` against the canonical data
root and do not permit a real catalog request.

- [ ] **Step 2: Record the development behavior**

Prove from source and temporary-path tests:

- whether the thread always starts under `--dev`;
- which database the main runtime locks when `CVM_DATA_DIR` is explicit;
- which database `_user_data_root()` selects for the refresh;
- whether `CVMANALYTICS_DATA_DIR` aligns both paths;
- all filesystem/database writes; and
- user-visible/log observability and opt-out availability.

- [ ] **Step 3: Record the packaged behavior**

Use source, `tests/test_desktop_runtime_paths.py`, and the stale isolated package
diagnostic from the design. Prove the normal frozen root, operator override,
console behavior, timeout/failure behavior, and write targets. Do not launch a
real online refresh.

- [ ] **Step 4: Record consumers and failure semantics**

Use exact `rg`/source references for company identity, company UI, sector
search, market-cap matching, distribution linking, and Excel export consumers.
Distinguish catalog-load failure, per-company failure, partial success, zero
valid updates, DB lock/write failure, TTL suppression, and next-start behavior.

- [ ] **Step 5: Post the evidence and options to the issue**

The issue comment includes source SHA, commands, environment, UTC timestamps,
durations, results, log locations, a dev/packaged comparison table, and options:

1. preserve current behavior but expose/gate it explicitly;
2. move it behind an explicit refresh/update action; or
3. remove the startup action and rely on explicit/local ingestion paths.

Recommend one option based on the local-first contract. Mark the issue
`status:needs-input`. Do not edit code, tests, docs, or workflows to change the
behavior. A reviewer independently checks the evidence and confirms the issue
is ready for João's explicit decision.

---

### Task 5: Define the release-publication evidence gate

**Issue title:** `[Investigation] Define release-publication evidence gate`

**Files:**
- Inspect: `.github/workflows/ci.yml`
- Inspect: `.github/workflows/release-desktop.yml`
- Inspect: `docs/build-release.md`
- Inspect: `desktop/build_desktop.ps1`
- Inspect: `desktop/updater.py` and updater tests only for preserved channel constraints
- Update: GitHub child issue body/comments only

**Interfaces:**
- Consumes: documented release preflight, current CI triggers/jobs, release tag workflow, package shape/checksum checks, and prior #372/#380/#382/#383 evidence.
- Produces: a verified coverage matrix and minimal proposal. It does not change publication behavior.

- [ ] **Step 1: Map documented checks to enforcement**

Build an issue table with one row per canonical preflight:

```text
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run test
npm --prefix apps/desktop-web run build
python scripts/data/check_storage_budget.py
python scripts/data/check_managed_ingestion_contracts.py --require-manifests --scan-sqlite-large-tables
python -m py_compile desktop/app.py desktop/bridge.py
python -m pytest tests -q
python -m pytest apps/api/tests -q
package provenance/version
ZIP root/checksum
clean/offline/copied-data/Excel/updater-boundary smoke
```

For each row record: current CI job, release job, manual-only status, evidence
artifact, failure behavior, and whether a release asset can publish without it.

- [ ] **Step 2: Verify trigger behavior from source and GitHub runs**

Record exact workflow trigger source and recent run URLs/SHAs. Confirm whether a
release tag receives a CI run and whether the release job depends on a successful
CI workflow or independently repeats checks.

- [ ] **Step 3: Produce the minimal proposal**

Propose the smallest enforceable relationship, such as a reusable verification
job/workflow or an explicit successful-SHA precondition. Include runtime,
failure/cancel behavior, permissions, artifact retention, rollback, and stable
versus prerelease preservation. Do not write YAML.

- [ ] **Step 4: Post and independently review the issue evidence**

Post source SHA, exact commands/API queries, environment, timestamps, durations,
results, and URLs/log locations. Mark `status:needs-input` and state plainly:
publication workflow changes require João's explicit approval. A reviewer
checks the matrix and proposal against `docs/build-release.md`; no PR is opened.

---

### Task 6: Validate a current-head packaged desktop candidate

**Issue title:** `[Validation] Verify a current-head packaged desktop candidate`

**Dependency:** Tasks 1-3 must be merged. Tasks 4-5 must have reviewed evidence;
their gated behavior remains unchanged.

**Files:**
- Create: `docs/architecture-hardening-wave-audit.md`
- Generated/ignored: `dist/CVMAnalytics/**`
- Generated/ignored: `scratch/architecture-hardening-wave/task-6/**`
- Do not modify: runtime source, database schemas/data, updater/release workflows, or version/channel contracts

**Interfaces:**
- Consumes: merged `main`, canonical build script and preflight commands, explicit `CVMANALYTICS_DATA_DIR`, disposable/copy-safe data fixtures, package diagnostic mode, Excel export, updater helper contract.
- Produces: a current-head candidate checksum/provenance package and durable final audit report. It publishes no release.

- [ ] **Step 1: Create and bootstrap the validation worktree**

Create from updated clean `origin/main` with the validation issue number, slug
`current-head-package-validation`, lane `ops-quality`, and base `main`. Record
the exact source SHA and require a clean worktree.

- [ ] **Step 2: Run and capture the full source preflight**

Run each separately with UTC timing and its own log/meta file:

```powershell
npm --prefix apps/desktop-web run test
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
python scripts/data/check_storage_budget.py
python scripts/data/check_managed_ingestion_contracts.py --require-manifests --scan-sqlite-large-tables
python -m py_compile desktop/app.py desktop/bridge.py
python -m pytest tests -q
python -m pytest apps/api/tests -q
python scripts/diagnostics/runtime_doctor.py --require-canonical
python scripts/diagnostics/benchmark_real_read_paths.py --runs 3
```

Expected: all pass. A failure is investigated and reported; it is never hidden
or converted to a pass. Do not use `--fail-on-backups` and do not run a managed
ingestion smoke with `--apply`.

- [ ] **Step 3: Build the local candidate without publishing**

```powershell
$validationVersion = python -c "from desktop.__version__ import __version__; print(__version__)"
.\desktop\build_desktop.ps1 -Version $validationVersion
```

Capture source SHA, resolved version, generated `desktop/_build_info.py`, start
and end timestamps, duration, exit code, build log, executable SHA-256, file
count/size, and `git status --short`. Do not create or push a tag. Generated
provenance/version changes must match the build script contract; no unrelated
tracked change is allowed.

- [ ] **Step 4: Create and verify a local ZIP artifact**

Create the ZIP under ignored task scratch, not the repository root:

```powershell
Compress-Archive -Path dist\CVMAnalytics\* `
  -DestinationPath scratch\architecture-hardening-wave\task-6\CVMAnalytics-current-head.zip `
  -CompressionLevel Optimal
Get-FileHash scratch\architecture-hardening-wave\task-6\CVMAnalytics-current-head.zip -Algorithm SHA256
```

Open the ZIP and assert its flat top-level roots are exactly
`CVMAnalytics.exe` and `_internal`. Record entry count, size, and checksum.

- [ ] **Step 5: Run a clean isolated frozen diagnostic**

Set only the documented operator root for the child process:

```powershell
New-Item -ItemType Directory -Force scratch\architecture-hardening-wave\task-6\clean-data | Out-Null
$env:CVMANALYTICS_DATA_DIR = (Resolve-Path scratch\architecture-hardening-wave\task-6\clean-data).Path
& .\dist\CVMAnalytics\CVMAnalytics.exe --diagnose-runtime --non-interactive
```

Expected: frozen runtime, version/build, WebView2/pythonnet, SQLite, and isolated
paths are explicit; no Documents production database is opened. Preserve the
diagnostic log.

- [ ] **Step 6: Validate copied-data and offline reads**

Create a disposable fixture under task scratch using SQLite backup/WAL-safe copy
procedures. Copy only the files required for representative company, status,
Energy, and Excel paths. Disconnect/deny network for the candidate process or
use a controlled no-network environment. Verify already-downloaded data remains
readable and missing/stale/source/error states remain visible.

Capture at least:

- company directory and company detail;
- financial readiness/statement path;
- Indicator Library/SIN cached path;
- Settings/Diagnostics paths and build provenance;
- no startup crash when offline; and
- unchanged copied-file hashes for input/raw/source-snapshot fixtures.

Do not use the canonical Documents databases directly.

- [ ] **Step 7: Validate package UI and normal laptop width**

Launch the packaged candidate against the disposable root. Use the real
pywebview/WebView2 runtime and capture screenshots/logs at 1366x768 and a wider
desktop viewport. Verify loading, empty, partial/error, offline, bridge-ready,
and normal navigation states without changing application state beyond the
disposable fixture.

- [ ] **Step 8: Validate Excel and updater boundaries**

Generate one representative company workbook into the disposable output root,
open it with the available spreadsheet validation runtime, and prove it opens
without repair. Record sheets, formulas/source sections, and file hash.

Exercise updater helper tests and package-contract checks only in disposable
install/data roots. Prove the allowlisted swap remains `CVMAnalytics.exe` plus
`_internal`, rollback is created, relaunch is issued, and user-data sentinels
are unchanged. Do not change the update channel or query/publish a prerelease as
stable.

- [ ] **Step 9: Write the durable final audit report**

Create `docs/architecture-hardening-wave-audit.md`. For every objective
requirement and child, record:

- status and authoritative evidence;
- issue and PR URLs;
- source/merge/candidate SHAs;
- exact command, environment, UTC timestamp, duration, pass/fail, log/artifact;
- files changed and behavioral invariants;
- review verdict and CI result;
- package/ZIP/Excel checksums and screenshot paths;
- data/root/source-snapshot preservation evidence;
- performance comparison; and
- remaining gated decisions/risks.

Distinguish pass, contradiction, incomplete, weak/indirect, and missing evidence.
Do not claim a packaged behavior from source-only or dev-only checks.

- [ ] **Step 10: Review, commit, and publish only the audit report**

```powershell
git add -- docs/architecture-hardening-wave-audit.md
git diff --cached --check
git commit -m "docs: record architecture hardening wave audit"
```

Generate the task review package, obtain specification and quality approval,
push/open a docs-only PR closing the validation child, and merge after checks.
Generated package/scratch files remain untracked and no release is published.

---

## Final program verification

After all authorized PRs merge and the audit PR is current:

- [ ] Confirm the Epic checklist links all six children and reflects their true states.
- [ ] Confirm Tasks 1-3 and 6 have focused reviewed PR evidence.
- [ ] Confirm Tasks 4-5 remain open/needs-input unless João separately approved implementation.
- [ ] Confirm no open PR, branch diff, or commit changed startup refresh behavior, publication behavior, database/public/financial/updater contracts, user-visible behavior, or `desktop/services.py` structure.
- [ ] Re-run final tests/checks at the final merged SHA and record provenance.
- [ ] Inspect the primary dirty checkout and prove its original user changes remain untouched.
- [ ] Search issues/PRs once more for duplicates and cross-link any newly overlapping work.
- [ ] Perform a requirement-by-requirement completion audit against the original goal and this design before marking the goal complete.
