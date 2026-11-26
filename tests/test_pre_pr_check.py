from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.diagnostics import pre_pr_check


def test_build_plan_always_includes_fast_ci_contract_mirror() -> None:
    plan = pre_pr_check.build_plan(changed_files={"README.md"}, python_exe="python")
    names = [step.name for step in plan]
    assert names == ["Governance & API contracts", "Compile desktop entry points"]
    assert "tests/test_api_runtime_contract.py" in plan[0].command
    assert "scripts/governance/test_frontend_ci_contract.py" in plan[0].command
    assert "desktop/app.py" in plan[1].command
    assert "desktop/bridge.py" in plan[1].command


def test_build_plan_adds_frontend_skills_and_storage_checks_for_matching_changes() -> None:
    changed = {
        "apps/desktop-web/src/App.tsx",
        ".agents/skills/ponytail/SKILL.md",
        "desktop/storage_inventory.py",
    }
    plan = pre_pr_check.build_plan(changed_files=changed, python_exe="python")
    names = [step.name for step in plan]
    assert names == [
        "Governance & API contracts",
        "Compile desktop entry points",
        "Verify vendored agent skills",
        "Agent skill updater tests",
        "Storage inventory tests",
        "Vite desktop UI tests",
        "Vite desktop UI typecheck",
        "Vite desktop UI build",
    ]


def test_build_plan_supports_full_python_and_all_flags() -> None:
    full_py = pre_pr_check.build_plan(changed_files=set(), python_exe="python", full_python=True)
    assert any(step.name == "Full Python & API test suite" for step in full_py)
    assert not any("Vite desktop UI" in step.name for step in full_py)

    all_steps = pre_pr_check.build_plan(changed_files=set(), python_exe="python", run_all=True)
    names = {step.name for step in all_steps}
    assert {
        "Governance & API contracts",
        "Compile desktop entry points",
        "Verify vendored agent skills",
        "Agent skill updater tests",
        "Storage inventory tests",
        "Vite desktop UI tests",
        "Vite desktop UI typecheck",
        "Vite desktop UI build",
        "Full Python & API test suite",
    } == names


def test_parse_porcelain_handles_modified_untracked_and_renamed_paths() -> None:
    porcelain = (
        " M apps/desktop-web/src/App.tsx\n"
        "?? scripts/diagnostics/pre_pr_check.py\n"
        "R  old/path.py -> desktop/storage_inventory.py\n"
    )
    assert pre_pr_check.parse_porcelain(porcelain) == {
        "apps/desktop-web/src/App.tsx",
        "scripts/diagnostics/pre_pr_check.py",
        "desktop/storage_inventory.py",
    }


def test_run_plan_fails_fast_and_dry_run_skips_execution() -> None:
    steps = [
        pre_pr_check.CheckStep("first", ["echo", "1"]),
        pre_pr_check.CheckStep("second", ["echo", "2"]),
    ]
    executed: list[list[str]] = []

    def fake_runner(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        executed.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=1 if cmd == ["echo", "1"] else 0)

    assert pre_pr_check.run_plan(steps, cwd=Path("."), dry_run=True, runner=fake_runner) == 0
    assert executed == []

    assert pre_pr_check.run_plan(steps, cwd=Path("."), dry_run=False, runner=fake_runner) == 1
    assert executed == [["echo", "1"]]


def test_build_plan_runs_existing_changed_python_tests_and_skips_deleted(tmp_path: Path) -> None:
    existing = tmp_path / "tests" / "test_sample.py"
    existing.parent.mkdir(parents=True)
    existing.write_text("def test_ok(): assert True\n", encoding="utf-8")

    plan = pre_pr_check.build_plan(
        changed_files={"tests/test_sample.py", "tests/test_deleted.py", "tests/test_api_runtime_contract.py"},
        python_exe="python",
        cwd=tmp_path,
    )
    changed_step = [s for s in plan if s.name == "Changed Python tests"]
    assert len(changed_step) == 1
    assert changed_step[0].command == ["python", "-m", "pytest", "tests/test_sample.py", "-q"]
