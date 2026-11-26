from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def _normalize_command(command: str) -> str:
    return re.sub(r"\s+", " ", command).strip()


def _blocking_named_run_steps_for_job(workflow_text: str, job_name: str) -> list[tuple[str, str]]:
    workflow = yaml.safe_load(workflow_text)
    jobs = workflow.get("jobs") or {}
    job = jobs.get(job_name)
    assert isinstance(job, dict), f"missing job: {job_name}"
    if "if" in job:
        raise AssertionError(f"required job {job_name!r} must not be conditional: {job['if']!r}")
    if job.get("continue-on-error") is True:
        raise AssertionError(f"required job {job_name!r} must not set continue-on-error")

    steps: list[tuple[str, str]] = []
    for step in job.get("steps") or []:
        if not isinstance(step, dict):
            continue
        name = step.get("name")
        run = step.get("run")
        if not name or not run:
            continue
        if "if" in step:
            continue
        if step.get("continue-on-error") is True:
            continue
        steps.append((str(name).strip(), _normalize_command(str(run))))
    return steps


def test_blocking_named_run_steps_ignore_disabled_or_nonblocking_steps() -> None:
    workflow = """
jobs:
  decoy:
    steps:
      - name: Test Vite desktop UI
        run: npm run test
  desktop-web:
    steps:
      # - name: Commented Vite decoy
      #   run: npm run test
      - name: Install Vite desktop UI dependencies
        run: npm ci
      - name: Disabled test
        if: false
        run: npm run test
      - name: Nonblocking typecheck
        continue-on-error: true
        run: npm run typecheck
      - name: Build Vite desktop UI
        run: npm run build
"""
    assert _blocking_named_run_steps_for_job(workflow, "desktop-web") == [
        ("Install Vite desktop UI dependencies", "npm ci"),
        ("Build Vite desktop UI", "npm run build"),
    ]


def test_blocking_named_run_steps_reject_conditional_job() -> None:
    workflow = """
jobs:
  desktop-web:
    if: false
    steps:
      - name: Test Vite desktop UI
        run: npm run test
"""
    with pytest.raises(AssertionError, match="must not be conditional"):
        _blocking_named_run_steps_for_job(workflow, "desktop-web")


def test_desktop_frontend_ci_runs_tests_before_typecheck_and_build() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    steps = iter(_blocking_named_run_steps_for_job(workflow, "desktop-web"))

    for expected in (
        ("Install Vite desktop UI dependencies", "npm ci"),
        ("Test Vite desktop UI", "npm run test"),
        ("Typecheck Vite desktop UI", "npm run typecheck"),
        ("Build Vite desktop UI", "npm run build"),
    ):
        assert any(step == expected for step in steps), f"missing blocking ordered step: {expected}"


def test_ci_collects_repository_governance_contracts() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    steps = _blocking_named_run_steps_for_job(workflow, "test-python")
    assert (
        "Run repository governance contract tests",
        "python -m pytest scripts/governance/test_repository_operational_contracts.py "
        "scripts/governance/test_frontend_ci_contract.py "
        "scripts/diagnostics/test_bridge_method_inventory.py "
        "scripts/governance/test_packaged_candidate_harness.py -q",
    ) in steps


def test_ci_runs_single_python_suite_with_coverage_and_pr_concurrency() -> None:
    workflow_text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)

    concurrency = workflow.get("concurrency")
    assert isinstance(concurrency, dict), "ci.yml must define concurrency to cancel superseded PR runs"
    assert concurrency.get("group") == "${{ github.workflow }}-${{ github.ref }}"
    assert concurrency.get("cancel-in-progress") == "${{ github.ref != 'refs/heads/main' }}"

    jobs = workflow["jobs"]
    assert jobs["test-python"].get("name") == "Python core tests"
    assert jobs["coverage-python"].get("name") == "Python core coverage"

    test_python_steps = _blocking_named_run_steps_for_job(workflow_text, "test-python")
    coverage_steps = _blocking_named_run_steps_for_job(workflow_text, "coverage-python")
    all_full_suite_steps = [
        cmd
        for _, cmd in (*test_python_steps, *coverage_steps)
        if "pytest tests apps/api/tests" in cmd
    ]
    assert len(all_full_suite_steps) == 1, "full Python suite must run once across CI jobs"
    assert "--cov=src" in all_full_suite_steps[0]
    assert "--cov=desktop" in all_full_suite_steps[0]
    assert "--cov-report=xml:coverage.xml" in all_full_suite_steps[0]

    step_names = [step.get("name") for step in jobs["coverage-python"]["steps"]]
    assert "Upload coverage artifact" in step_names
    assert "Upload coverage to Codecov" in step_names
