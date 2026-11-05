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
    commands = [step.get("run", "") for step in workflow["jobs"]["test-python"]["steps"]]
    assert any("pytest" in command and "apps/api/tests" in command for command in commands)
