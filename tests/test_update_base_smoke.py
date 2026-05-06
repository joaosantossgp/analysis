from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "update_base_smoke",
    _ROOT / "scripts" / "update_base_smoke.py",
)
assert _SPEC and _SPEC.loader
ubs = importlib.util.module_from_spec(_SPEC)
sys.modules["update_base_smoke"] = ubs
_SPEC.loader.exec_module(ubs)


def test_build_batch_body_includes_limit_and_mode():
    body = ubs.build_batch_body(
        mode="missing",
        limit=1,
        cd_cvm=9512,
        sector_slug=None,
        cvm_from=None,
        cvm_to=None,
        start_year=2023,
        end_year=2024,
        status_filter=None,
        search=None,
    )
    assert body == {
        "mode": "missing",
        "limit": 1,
        "cd_cvm": 9512,
        "start_year": 2023,
        "end_year": 2024,
    }


def test_validate_live_guardrails_blocks_without_confirm():
    with pytest.raises(SystemExit) as exc:
        ubs.validate_live_guardrails(
            dry_run=False,
            confirm_live=False,
            limit=1,
            allow_large_batch=False,
        )
    assert int(exc.value.code) == 2


def test_validate_live_guardrails_allows_dry_run():
    ubs.validate_live_guardrails(
        dry_run=True,
        confirm_live=False,
        limit=500,
        allow_large_batch=False,
    )


def test_validate_live_guardrails_blocks_large_limit():
    with pytest.raises(SystemExit) as exc:
        ubs.validate_live_guardrails(
            dry_run=False,
            confirm_live=True,
            limit=100,
            allow_large_batch=False,
        )
    assert int(exc.value.code) == 2


def test_run_web_smoke_dry_run():
    evidence = ubs.run_web_smoke(
        api_base="http://127.0.0.1:8000",
        body={"mode": "missing", "limit": 1},
        dry_run=True,
        poll_interval=0.01,
        poll_timeout=1.0,
        cancel_after_running=False,
    )
    assert evidence.dry_run is True
    assert evidence.dispatch and evidence.dispatch.get("status") == "dry_run"


def test_run_web_smoke_happy_path_mocked():
    job_id = "abc123"
    snapshots = [
        {
            "job_id": job_id,
            "state": "running",
            "status": "running",
            "queued": 1,
            "processed": 0,
            "failures": 0,
            "log_lines": [],
        },
        {
            "job_id": job_id,
            "state": "success",
            "status": "success",
            "queued": 1,
            "processed": 1,
            "failures": 0,
            "log_lines": ["ok"],
        },
    ]

    def fake_post(url, **kwargs):
        if url.endswith("/refresh/batch"):
            return SimpleNamespace(
                status_code=202,
                json=lambda: {
                    "status": "running",
                    "job_id": job_id,
                    "queued": 1,
                    "message": "started",
                },
            )
        if url.endswith("/cancel"):
            return SimpleNamespace(
                status_code=200,
                json=lambda: {"ok": True, "job_id": job_id, "state": "running"},
            )
        raise AssertionError(f"unexpected post {url}")

    calls: list[str] = []

    def fake_get(url, **kwargs):
        calls.append(url)
        snap = snapshots[min(len(calls) - 1, len(snapshots) - 1)]
        return SimpleNamespace(status_code=200, json=lambda: snap)

    evidence = ubs.run_web_smoke(
        api_base="http://127.0.0.1:8000",
        body={"mode": "missing", "limit": 1, "cd_cvm": 9512},
        dry_run=False,
        poll_interval=0.0,
        poll_timeout=5.0,
        cancel_after_running=False,
        post_fn=fake_post,
        get_fn=fake_get,
    )
    assert evidence.dispatch and evidence.dispatch["job_id"] == job_id
    assert evidence.terminal_state == "success"
    assert evidence.job_snapshots
    assert evidence.job_snapshots[-1]["state"] == "success"


def test_run_desktop_smoke_dry_run():
    evidence = ubs.run_desktop_smoke(
        body={"mode": "missing", "limit": 1},
        dry_run=True,
        poll_interval=0.01,
        poll_timeout=1.0,
        cancel_after_running=False,
    )
    assert evidence.profile == "desktop"
    assert evidence.dispatch and evidence.dispatch.get("status") == "dry_run"


def test_run_desktop_smoke_with_fake_bridge():
    class FakeBridge:
        def __init__(self) -> None:
            self._phase = 0

        def request_refresh(self, params):
            return {
                "status": "running",
                "job_id": "j1",
                "queued": 1,
                "message": "ok",
            }

        def get_refresh_status(self, params):
            self._phase += 1
            if self._phase == 1:
                return {
                    "state": "running",
                    "job_id": "j1",
                    "queued": 1,
                    "processed": 0,
                    "failures": 0,
                    "log_lines": [],
                }
            return {
                "state": "success",
                "job_id": "j1",
                "queued": 1,
                "processed": 1,
                "failures": 0,
                "log_lines": ["done"],
            }

        def cancel_refresh(self, params):
            return {"ok": True, "message": "cancel"}

    evidence = ubs.run_desktop_smoke(
        body={"mode": "missing", "limit": 1},
        dry_run=False,
        poll_interval=0.0,
        poll_timeout=3.0,
        cancel_after_running=False,
        bridge_factory=FakeBridge,
    )
    assert evidence.terminal_state == "success"


def test_main_json_outputs_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(
        ubs,
        "run_web_smoke",
        lambda **kwargs: ubs.SmokeEvidence(
            profile="web",
            api_base="http://x",
            dry_run=True,
            batch_body={"mode": "missing"},
            dispatch={"status": "dry_run"},
        ),
    )
    code = ubs.main(["--dry-run", "--json"])
    assert code == 0
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload["profile"] == "web"
    assert payload["dispatch"]["status"] == "dry_run"
