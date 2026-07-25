from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _named_run_steps_for_job(workflow: str, job_name: str) -> list[tuple[str, str]]:
    job_header = re.compile(r"^  (?P<name>[A-Za-z0-9_-]+):\s*$")
    step_name = re.compile(r"^      - name:\s*(?P<name>.+?)\s*$")
    step_run = re.compile(r"^        run:\s*(?P<command>\S.*?)\s*$")
    jobs_started = False
    in_job = False
    in_steps = False
    current_name: str | None = None
    steps: list[tuple[str, str]] = []

    for line in workflow.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line == "jobs:":
            jobs_started = True
            continue
        if not jobs_started:
            continue

        job_match = job_header.fullmatch(line)
        if job_match:
            if in_job:
                break
            in_job = job_match.group("name") == job_name
            in_steps = False
            current_name = None
            continue
        if not in_job:
            continue
        if line == "    steps:":
            in_steps = True
            continue
        if not in_steps:
            continue

        name_match = step_name.fullmatch(line)
        if name_match:
            current_name = name_match.group("name")
            continue
        if line.startswith("      - "):
            current_name = None
            continue

        run_match = step_run.fullmatch(line)
        if current_name is not None and run_match:
            steps.append((current_name, run_match.group("command")))
            current_name = None

    return steps


def test_named_run_steps_are_scoped_to_job_and_ignore_comments() -> None:
    workflow = """
jobs:
  decoy:
    steps:
      - name: Test Vite desktop UI
        run: npm run test
      - name: Run repository governance contract tests
        run: python -m pytest scripts/governance/test_repository_operational_contracts.py scripts/governance/test_frontend_ci_contract.py -q
  test-python:
    steps:
      # - name: Commented governance decoy
      #   run: python -m pytest scripts/governance/test_repository_operational_contracts.py scripts/governance/test_frontend_ci_contract.py -q
      - name: Run repository governance contract tests
        run: python -m pytest scripts/governance/test_repository_operational_contracts.py scripts/governance/test_frontend_ci_contract.py -q
  desktop-web:
    steps:
      # - name: Commented Vite decoy
      #   run: npm run test
      - name: Install Vite desktop UI dependencies
        run: npm ci
      - name: Test Vite desktop UI
        run: npm run test
      - name: Typecheck Vite desktop UI
        run: npm run typecheck
      - name: Build Vite desktop UI
        run: npm run build
"""

    assert _named_run_steps_for_job(workflow, "desktop-web") == [
        ("Install Vite desktop UI dependencies", "npm ci"),
        ("Test Vite desktop UI", "npm run test"),
        ("Typecheck Vite desktop UI", "npm run typecheck"),
        ("Build Vite desktop UI", "npm run build"),
    ]
    assert _named_run_steps_for_job(workflow, "test-python") == [
        (
            "Run repository governance contract tests",
            "python -m pytest "
            "scripts/governance/test_repository_operational_contracts.py "
            "scripts/governance/test_frontend_ci_contract.py -q",
        )
    ]


def test_desktop_frontend_ci_runs_tests_before_typecheck_and_build() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    steps = iter(_named_run_steps_for_job(workflow, "desktop-web"))

    for expected in (
        ("Install Vite desktop UI dependencies", "npm ci"),
        ("Test Vite desktop UI", "npm run test"),
        ("Typecheck Vite desktop UI", "npm run typecheck"),
        ("Build Vite desktop UI", "npm run build"),
    ):
        assert any(step == expected for step in steps), f"missing ordered step: {expected}"


def test_ci_collects_repository_governance_contracts() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    steps = _named_run_steps_for_job(workflow, "test-python")
    assert (
        "Run repository governance contract tests",
        "python -m pytest scripts/governance/test_repository_operational_contracts.py "
        "scripts/governance/test_frontend_ci_contract.py "
        "scripts/diagnostics/test_bridge_method_inventory.py "
        "scripts/governance/test_packaged_candidate_harness.py -q",
    ) in steps
