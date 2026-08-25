from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def _workflow(name: str) -> dict[str, object]:
    payload = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    payload["triggers"] = payload.get("on", payload.get(True))
    return payload


def test_external_workflows_have_no_automatic_trigger() -> None:
    for name in ("deploy-landing.yml", "refresh.yml"):
        assert set(_workflow(name)["triggers"]) == {"workflow_dispatch"}, name


def test_external_workflow_jobs_are_hard_disabled() -> None:
    expected_conditions = {
        "deploy-landing.yml": {"deploy": "${{ false }}"},
        "ingest.yml": {"ingest": "${{ false }}"},
        "refresh.yml": {"refresh": "${{ false }}"},
        "release-desktop.yml": {
            "resolve-candidate": "${{ false && inputs.phase == 'candidate' }}",
            "build-windows": "${{ false && inputs.phase == 'candidate' }}",
            "attest-evidence": "${{ false && inputs.phase == 'attest' }}",
            "publish-preflight": "${{ false && inputs.phase == 'publish' }}",
            "final-publish": "${{ false && inputs.phase == 'publish' }}",
        },
    }

    for workflow_name, jobs in expected_conditions.items():
        workflow_jobs = _workflow(workflow_name)["jobs"]
        assert {name: workflow_jobs[name].get("if") for name in jobs} == jobs
