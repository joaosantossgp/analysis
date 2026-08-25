from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def _workflow(name: str) -> dict[str, object]:
    payload = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    payload["triggers"] = payload.get("on", payload.get(True))
    return payload


def test_external_workflow_inventory_covers_all_risk_signals() -> None:
    risk_signals = ("secrets.DATABASE_URL", "actions/deploy-pages", "contents: write")
    discovered = {
        path.name
        for path in WORKFLOWS.glob("*.yml")
        if any(signal in path.read_text(encoding="utf-8") for signal in risk_signals)
    }
    assert discovered == {
        "backfill_historico.yml",
        "deploy-landing.yml",
        "ingest.yml",
        "on_demand_ingest.yml",
        "refresh.yml",
        "release-desktop.yml",
        "seed_catalog.yml",
    }


def test_external_workflows_have_no_automatic_trigger() -> None:
    for name in (
        "backfill_historico.yml",
        "deploy-landing.yml",
        "ingest.yml",
        "on_demand_ingest.yml",
        "refresh.yml",
        "release-desktop.yml",
        "seed_catalog.yml",
    ):
        assert set(_workflow(name)["triggers"]) == {"workflow_dispatch"}, name


def test_external_workflow_jobs_are_hard_disabled() -> None:
    expected_conditions = {
        "backfill_historico.yml": {
            "full-load": "${{ false && github.event_name == 'workflow_dispatch' }}",
            "gap-fill": "${{ false && github.event_name == 'schedule' }}",
        },
        "deploy-landing.yml": {"deploy": "${{ false }}"},
        "ingest.yml": {"ingest": "${{ false }}"},
        "on_demand_ingest.yml": {"ingest": "${{ false }}"},
        "refresh.yml": {"refresh": "${{ false }}"},
        "release-desktop.yml": {
            "resolve-candidate": "${{ false && inputs.phase == 'candidate' }}",
            "build-windows": "${{ false && inputs.phase == 'candidate' }}",
            "attest-evidence": "${{ false && inputs.phase == 'attest' }}",
            "publish-preflight": "${{ false && inputs.phase == 'publish' }}",
            "final-publish": "${{ false && inputs.phase == 'publish' }}",
        },
        "seed_catalog.yml": {"seed-catalog": "${{ false }}"},
    }

    for workflow_name, jobs in expected_conditions.items():
        workflow_jobs = _workflow(workflow_name)["jobs"]
        assert set(workflow_jobs) == set(jobs), workflow_name
        assert {name: workflow_jobs[name].get("if") for name in workflow_jobs} == jobs
