from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[2]

GOVERNANCE_TESTS = (
    "scripts/governance/test_repository_operational_contracts.py",
    "scripts/governance/test_frontend_ci_contract.py",
    "scripts/diagnostics/test_bridge_method_inventory.py",
    "scripts/governance/test_packaged_candidate_harness.py",
    "tests/test_api_runtime_contract.py",
)

SKILL_PATHS = (
    ".agents/skills/",
    "scripts/governance/update_agent_skills.py",
    "scripts/governance/test_update_agent_skills.py",
    ".github/workflows/update-agent-skills.yml",
)

STORAGE_PATHS = (
    "desktop/storage_inventory.py",
    "tests/test_storage_inventory.py",
)


@dataclass(frozen=True)
class CheckStep:
    name: str
    command: list[str]


Runner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


def parse_porcelain(output: str) -> set[str]:
    paths: set[str] = set()
    for line in output.splitlines():
        if len(line) < 4:
            continue
        raw = line[3:].strip()
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[1].strip()
        if raw:
            paths.add(raw.replace("\\", "/").strip('"'))
    return paths


def _git_output(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def detect_changed_files(cwd: Path, base: str | None = None) -> set[str]:
    changed: set[str] = set()
    candidates = [base] if base else ["origin/main", "main"]
    for ref in candidates:
        diff = _git_output(["diff", "--name-only", f"{ref}...HEAD"], cwd)
        if diff.returncode == 0:
            changed.update(
                line.strip().replace("\\", "/")
                for line in diff.stdout.splitlines()
                if line.strip()
            )
            break

    status = _git_output(["status", "--porcelain"], cwd)
    if status.returncode == 0:
        changed.update(parse_porcelain(status.stdout))
    return changed


def _matches_any(changed_files: set[str], prefixes: tuple[str, ...]) -> bool:
    return any(
        path == prefix or path.startswith(prefix)
        for path in changed_files
        for prefix in prefixes
    )


def _changed_test_targets(changed_files: set[str], cwd: Path | None) -> list[str]:
    already = set(GOVERNANCE_TESTS) | set(STORAGE_PATHS)
    targets = sorted(
        path
        for path in changed_files
        if path not in already
        and path.startswith(("tests/", "apps/api/tests/"))
        and Path(path).name.startswith("test_")
        and path.endswith(".py")
        and (cwd is None or (cwd / path).is_file())
    )
    return targets


def build_plan(
    *,
    changed_files: set[str],
    python_exe: str = sys.executable,
    npm_exe: str | None = None,
    cwd: Path | None = None,
    full_python: bool = False,
    run_all: bool = False,
) -> list[CheckStep]:
    npm = npm_exe or shutil.which("npm") or "npm"
    steps = [
        CheckStep(
            "Governance & API contracts",
            [python_exe, "-m", "pytest", *GOVERNANCE_TESTS, "-q"],
        ),
        CheckStep(
            "Compile desktop entry points",
            [python_exe, "-m", "py_compile", "desktop/app.py", "desktop/bridge.py"],
        ),
    ]

    if not (run_all or full_python):
        changed_tests = _changed_test_targets(changed_files, cwd)
        if changed_tests:
            steps.append(
                CheckStep(
                    "Changed Python tests",
                    [python_exe, "-m", "pytest", *changed_tests, "-q"],
                )
            )

    if run_all or _matches_any(changed_files, SKILL_PATHS):
        steps.append(
            CheckStep(
                "Verify vendored agent skills",
                [python_exe, "scripts/governance/update_agent_skills.py", "--verify"],
            )
        )
        steps.append(
            CheckStep(
                "Agent skill updater tests",
                [python_exe, "-m", "unittest", "scripts.governance.test_update_agent_skills"],
            )
        )

    if run_all or _matches_any(changed_files, STORAGE_PATHS):
        steps.append(
            CheckStep(
                "Storage inventory tests",
                [python_exe, "-m", "pytest", "tests/test_storage_inventory.py", "-q"],
            )
        )

    if run_all or _matches_any(changed_files, ("apps/desktop-web/",)):
        steps.extend(
            [
                CheckStep("Vite desktop UI tests", [npm, "--prefix", "apps/desktop-web", "run", "test"]),
                CheckStep("Vite desktop UI typecheck", [npm, "--prefix", "apps/desktop-web", "run", "typecheck"]),
                CheckStep("Vite desktop UI build", [npm, "--prefix", "apps/desktop-web", "run", "build"]),
            ]
        )

    if run_all or full_python:
        steps.append(
            CheckStep(
                "Full Python & API test suite",
                [python_exe, "-m", "pytest", "tests", "apps/api/tests", "-q"],
            )
        )

    return steps


def _default_runner(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, check=False)


def run_plan(
    steps: list[CheckStep],
    *,
    cwd: Path,
    dry_run: bool = False,
    runner: Runner = _default_runner,
) -> int:
    started = time.monotonic()
    for step in steps:
        rendered = " ".join(step.command)
        if dry_run:
            print(f"[dry-run] {step.name}: {rendered}", flush=True)
            continue
        t0 = time.monotonic()
        print(f"==> {step.name}", flush=True)
        result = runner(step.command, cwd)
        elapsed = time.monotonic() - t0
        if result.returncode != 0:
            print(f"FAIL {step.name} ({elapsed:.1f}s, exit {result.returncode})", flush=True)
            return result.returncode
        print(f"OK   {step.name} ({elapsed:.1f}s)", flush=True)
    if not dry_run:
        print(f"All {len(steps)} pre-PR checks passed in {time.monotonic() - started:.1f}s.", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run local CI contract mirror and changed-area checks before opening a PR."
    )
    parser.add_argument("--base", help="Base git ref for changed-file detection (default: origin/main or main).")
    parser.add_argument("--full-python", action="store_true", help="Also run pytest tests apps/api/tests.")
    parser.add_argument("--all", dest="run_all", action="store_true", help="Run every check regardless of git diff.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned checks without executing them.")
    args = parser.parse_args(argv)

    changed = set() if args.run_all else detect_changed_files(ROOT, base=args.base)
    steps = build_plan(
        changed_files=changed,
        python_exe=sys.executable,
        cwd=ROOT,
        full_python=args.full_python,
        run_all=args.run_all,
    )
    return run_plan(steps, cwd=ROOT, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
