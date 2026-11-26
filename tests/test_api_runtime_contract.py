from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_api_process_local_jobs_use_single_worker_container():
    dockerfile = (ROOT / "apps/api/Dockerfile").read_text(encoding="utf-8")
    command = next(line for line in dockerfile.splitlines() if line.startswith("CMD "))
    assert "--workers 1 " in command
    assert "WEB_CONCURRENCY" not in command


def test_ci_executes_api_tests():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    commands = [
        step.get("run", "")
        for job_name in ("test-python", "coverage-python")
        if job_name in jobs and "if" not in jobs[job_name]
        for step in jobs[job_name].get("steps", [])
        if "if" not in step and step.get("continue-on-error") is not True
    ]
    assert any("pytest" in command and "apps/api/tests" in command for command in commands)


def test_api_metadata_does_not_claim_read_only():
    main_source = (ROOT / "apps/api/app/main.py").read_text(encoding="utf-8")
    assert "read-only" not in main_source.lower()
    assert "explicit refresh" in main_source.lower()
