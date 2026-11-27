"""Dev bridge contract: dev context, restart, auto-restart (#610) and dev data actions (#614)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from desktop import dev_data, dev_supervisor
from desktop.bridge import CVMBridge
from desktop.bridge_api import dev as dev_bridge

CLEAN = "# branch.oid 6b755610aa11bb22cc33dd44ee55ff6677889900\n# branch.head feat/610-dev-panel\n"
DIRTY = CLEAN + "1 .M N... 100644 100644 100644 abc def desktop/app.py\n? notes.txt\n"


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A worktree of a main checkout, with git answers and data paths faked."""
    main, worktree = tmp_path / "main", tmp_path / "wt-610"
    worktree.mkdir(parents=True)
    main.mkdir()
    monkeypatch.setattr(dev_bridge, "_repo_root", lambda: worktree)
    monkeypatch.setattr(dev_bridge, "_git_status", lambda _root: CLEAN)
    monkeypatch.setattr(dev_data, "main_checkout", lambda _root: main)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    for name in ("CVM_DATA_DIR", "CVMANALYTICS_USE_RELEASE_DATA", dev_supervisor.CONTROL_DIR_ENV):
        monkeypatch.delenv(name, raising=False)
    return worktree


@pytest.fixture
def control_dir(checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The app runs under a dev supervisor that published its first status."""
    path = tmp_path / "control"
    path.mkdir()
    dev_supervisor.write_status(path, {"auto_restart": True, "pending_changes": 0})
    monkeypatch.setenv(dev_supervisor.CONTROL_DIR_ENV, str(path))
    return path


# --- git status parsing --------------------------------------------------------


def test_git_status_parsing_reads_branch_commit_and_dirty_state() -> None:
    assert dev_bridge.parse_git_status(CLEAN) == {"branch": "feat/610-dev-panel", "commit": "6b75561", "dirty": False}
    assert dev_bridge.parse_git_status(DIRTY)["dirty"] is True
    assert dev_bridge.parse_git_status(CLEAN + "? only-untracked.txt\n")["dirty"] is True


def test_git_status_parsing_keeps_unknown_values_missing() -> None:
    detached = "# branch.oid 6b755610aa11bb22cc33dd44ee55ff6677889900\n# branch.head (detached)\n"
    assert dev_bridge.parse_git_status(detached) == {"branch": None, "commit": "6b75561", "dirty": False}

    unborn = "# branch.oid (initial)\n# branch.head main\n"
    assert dev_bridge.parse_git_status(unborn) == {"branch": "main", "commit": None, "dirty": False}


# --- dev_get_context -----------------------------------------------------------


def test_context_describes_a_worktree_on_shared_dev_data(checkout: Path, control_dir: Path) -> None:
    result = CVMBridge().dev_get_context()

    assert result == {
        "ok": True,
        "worktree": "wt-610",
        "worktree_path": str(checkout),
        "is_main_checkout": False,
        "branch": "feat/610-dev-panel",
        "commit": "6b75561",
        "dirty": False,
        "git_error": None,
        "data_mode": "shared",
        "data_path": str(checkout.parent / "main" / "data" / "dev-runtime"),
        "supervised": True,
        "auto_restart": True,
        "pending_changes": 0,
    }


def test_context_reports_uncommitted_changes(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dev_bridge, "_git_status", lambda _root: DIRTY)

    assert CVMBridge().dev_get_context()["dirty"] is True


def test_context_marks_the_main_checkout(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dev_data, "main_checkout", lambda _root: checkout)

    result = CVMBridge().dev_get_context()

    assert result["is_main_checkout"] is True
    assert result["data_mode"] == "shared"
    assert result["data_path"] == str(checkout / "data" / "dev-runtime")


@pytest.mark.parametrize("marker", ["isolated", "full-copy"])
def test_context_reports_isolated_dev_data_of_a_data_sensitive_worktree(checkout: Path, marker: str) -> None:
    (checkout / dev_data.MARKER_NAME).write_text(marker + "\n", encoding="utf-8")

    result = CVMBridge().dev_get_context()

    assert result["data_mode"] == marker
    assert result["data_path"] == str(checkout / "data" / "dev-runtime")


def test_context_reports_an_explicit_data_directory_as_custom(
    checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (checkout / dev_data.MARKER_NAME).write_text("isolated\n", encoding="utf-8")
    monkeypatch.setenv("CVM_DATA_DIR", str(tmp_path / "throwaway"))

    result = CVMBridge().dev_get_context()

    assert result["data_mode"] == "custom"
    assert result["data_path"] == str(tmp_path / "throwaway")


def test_context_follows_the_data_directory_the_launcher_resolved(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shared = checkout.parent / "main" / "data" / "dev-runtime"
    monkeypatch.setenv("CVM_DATA_DIR", str(shared))

    assert CVMBridge().dev_get_context()["data_mode"] == "shared"


def test_context_reports_installed_app_data_mode(checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CVMANALYTICS_USE_RELEASE_DATA", "1")
    monkeypatch.setenv("CVM_DATA_DIR", str(tmp_path / "Documents" / "CVMAnalytics"))

    result = CVMBridge().dev_get_context()

    assert result["data_mode"] == "installed-app"
    assert result["data_path"] == str(tmp_path / "Documents" / "CVMAnalytics")


def test_context_keeps_git_values_missing_when_git_fails(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def git_fails(_root: Path) -> str:
        raise OSError("git not found")

    monkeypatch.setattr(dev_bridge, "_git_status", git_fails)

    result = CVMBridge().dev_get_context()

    assert result["ok"] is True
    assert (result["branch"], result["commit"], result["dirty"]) == (None, None, None)
    assert "git not found" in result["git_error"]
    assert result["data_mode"] == "shared", "the data context does not depend on git status"


def test_context_without_a_supervisor_has_no_restart_state(checkout: Path) -> None:
    result = CVMBridge().dev_get_context()

    assert result["supervised"] is False
    assert result["auto_restart"] is None
    assert result["pending_changes"] is None


def test_context_reports_a_failure_instead_of_raising(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(_root: Path) -> Path:
        raise RuntimeError("worktree list exploded")

    monkeypatch.setattr(dev_data, "main_checkout", broken)

    result = CVMBridge().dev_get_context()

    assert result["ok"] is False
    assert "worktree list exploded" in result["error"]


# --- dev_restart / dev_set_auto_restart ----------------------------------------


def test_restart_queues_a_request_for_the_supervisor(control_dir: Path) -> None:
    assert CVMBridge().dev_restart() == {"ok": True}

    assert dev_supervisor.read_requests(control_dir) == [{"action": "restart"}]


def test_set_auto_restart_returns_the_state_the_supervisor_confirmed(
    control_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    supervisor = dev_supervisor.DevSupervisor(
        start_child=lambda: None,
        stop_child=lambda _child: None,
        scan=dict,
        report=lambda _message: None,
        read_requests=lambda: dev_supervisor.read_requests(control_dir),
        publish_status=lambda status: dev_supervisor.write_status(control_dir, status),
    )
    # The bridge waits for the supervisor; each wait is one supervisor poll.
    monkeypatch.setattr(dev_bridge.time, "sleep", lambda _seconds: supervisor.tick(0.0))

    assert CVMBridge().dev_set_auto_restart({"enabled": False}) == {"ok": True, "auto_restart": False}
    assert CVMBridge().dev_get_context()["auto_restart"] is False
    assert CVMBridge().dev_set_auto_restart({"enabled": True}) == {"ok": True, "auto_restart": True}


def test_set_auto_restart_fails_when_the_supervisor_does_not_confirm(
    control_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dev_bridge.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(dev_bridge, "CONFIRM_TIMEOUT_SECONDS", 0.0)

    result = CVMBridge().dev_set_auto_restart({"enabled": False})

    assert result["ok"] is False
    assert "did not confirm" in result["error"]


@pytest.mark.parametrize("params", [None, {}, {"enabled": "yes"}, {"enabled": 1}])
def test_set_auto_restart_rejects_anything_but_a_boolean(control_dir: Path, params: dict | None) -> None:
    result = CVMBridge().dev_set_auto_restart(params)

    assert result["ok"] is False
    assert dev_supervisor.read_requests(control_dir) == []


def test_restart_controls_fail_plainly_without_a_supervisor(checkout: Path) -> None:
    for result in (CVMBridge().dev_restart(), CVMBridge().dev_set_auto_restart({"enabled": False})):
        assert result["ok"] is False
        assert "supervisor" in result["error"]


# --- packaged app --------------------------------------------------------------


def test_dev_methods_refuse_in_the_packaged_app(control_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(dev_bridge, "_git_status", lambda _root: pytest.fail("the packaged app must not run git"))
    bridge = CVMBridge()

    for result in (bridge.dev_get_context(), bridge.dev_restart(), bridge.dev_set_auto_restart({"enabled": False})):
        assert result["ok"] is False
        assert result["status"] == "blocked"
        assert result["status_reason_code"] == "dev_mode_only"
        assert result["error"]
    assert dev_supervisor.read_requests(control_dir) == [], "a refused call reaches no supervisor"


# --- dev data actions (#614) ---------------------------------------------------


@pytest.fixture
def shared_data(checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Shared dev data of a main checkout that is a git checkout; the profile is a temp folder."""
    main = checkout.parent / "main"
    (main / ".git").mkdir()
    shared = main / "data" / "dev-runtime"
    (shared / "db").mkdir(parents=True)
    (shared / "db" / "cvm_financials.db").write_bytes(b"x" * 2048)
    (shared / "input").mkdir()
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "profile"))
    monkeypatch.delenv("CVMANALYTICS_DATA_DIR", raising=False)
    return shared


ACTIONS = ("dev_move_data_to_backup", "dev_restore_data_backup", "dev_delete_data")


def test_data_info_lists_the_targets_with_sizes_and_backups(shared_data: Path, control_dir: Path) -> None:
    result = CVMBridge().dev_get_data_info()

    assert result["ok"] is True
    assert result["unavailable_reason"] is None
    assert result["supervised"] is True
    assert result["last_action"] is None
    assert [t["target"] for t in result["targets"]] == ["db", "input", "all"]
    db = result["targets"][0]
    assert (db["path"], db["size_bytes"], db["shared"], db["backup_exists"]) == (str(shared_data / "db"), 2048, True, False)


def test_data_info_reports_the_last_data_action_of_the_session(shared_data: Path, control_dir: Path) -> None:
    outcome = {"operation": "backup", "target": "db", "ok": False, "message": "Data action failed: locked.",
               "finished_at": "2026-11-27 10:00:00"}
    (control_dir / dev_supervisor.DATA_ACTION_FILE).write_text(json.dumps(outcome), encoding="utf-8")

    assert CVMBridge().dev_get_data_info()["last_action"] == outcome


def test_move_to_backup_hands_the_resolved_dev_data_to_the_supervisor(shared_data: Path, control_dir: Path) -> None:
    assert CVMBridge().dev_move_data_to_backup({"target": "db"}) == {"ok": True}

    assert dev_supervisor.read_requests(control_dir) == [
        {
            "action": "data_action",
            "operation": "backup",
            "target": "db",
            "mode": "shared",
            "data_root": str(shared_data),
            "shared_root": str(shared_data),
        }
    ]
    assert (shared_data / "db" / "cvm_financials.db").exists(), "the bridge never touches data itself"


def test_delete_needs_the_target_typed_again(shared_data: Path, control_dir: Path) -> None:
    for params in ({"target": "db"}, {"target": "db", "confirm": "all"}):
        result = CVMBridge().dev_delete_data(params)
        assert result["ok"] is False
        assert "Type db to confirm" in result["error"]
    assert dev_supervisor.read_requests(control_dir) == []

    assert CVMBridge().dev_delete_data({"target": "db", "confirm": "db"}) == {"ok": True}
    assert dev_supervisor.read_requests(control_dir)[0]["operation"] == "delete"


@pytest.mark.parametrize(
    ("method", "params", "expected"),
    [
        ("dev_restore_data_backup", {"target": "db"}, "no Database backup"),
        ("dev_move_data_to_backup", {"target": "logs"}, "Unknown data target"),
        ("dev_move_data_to_backup", None, "Unknown data target"),
    ],
)
def test_actions_that_cannot_run_fail_before_the_window_closes(
    shared_data: Path, control_dir: Path, method: str, params: dict | None, expected: str
) -> None:
    result = getattr(CVMBridge(), method)(params)

    assert result["ok"] is False
    assert expected in result["error"]
    assert dev_supervisor.read_requests(control_dir) == []


def test_data_actions_fail_plainly_without_a_supervisor(shared_data: Path) -> None:
    result = CVMBridge().dev_move_data_to_backup({"target": "db"})

    assert result["ok"] is False
    assert "supervisor" in result["error"]
    assert CVMBridge().dev_get_data_info()["supervised"] is False


@pytest.mark.parametrize("variable", ["CVMANALYTICS_USE_RELEASE_DATA", "CVM_DATA_DIR"])
def test_data_actions_refuse_installed_app_and_custom_data(
    shared_data: Path, control_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    monkeypatch.setenv(variable, str(tmp_path / "custom") if variable == "CVM_DATA_DIR" else "1")
    bridge = CVMBridge()

    info = bridge.dev_get_data_info()
    assert info["ok"] is True
    assert variable in info["unavailable_reason"]
    assert info["targets"] == [], "no sizes or paths of data the panel may not act on"
    for method in ACTIONS:
        result = getattr(bridge, method)({"target": "db", "confirm": "db"})
        assert result["status"] == "blocked"
        assert result["status_reason_code"] == "dev_data_actions_unavailable"
    assert dev_supervisor.read_requests(control_dir) == []


def test_data_actions_refuse_when_the_main_checkout_lies_inside_installed_app_data(
    checkout: Path, control_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    documents_checkout = tmp_path / "profile" / "Documents" / "CVMAnalytics"
    (documents_checkout / ".git").mkdir(parents=True)
    monkeypatch.setattr(dev_data, "main_checkout", lambda _root: documents_checkout)
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "profile"))

    assert "installed-app data" in CVMBridge().dev_get_data_info()["unavailable_reason"]
    assert CVMBridge().dev_move_data_to_backup({"target": "all"})["status"] == "blocked"
    assert dev_supervisor.read_requests(control_dir) == []


def test_data_methods_refuse_in_the_packaged_app(shared_data: Path, control_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    bridge = CVMBridge()

    results = [bridge.dev_get_data_info()] + [getattr(bridge, m)({"target": "db", "confirm": "db"}) for m in ACTIONS]
    for result in results:
        assert result["ok"] is False
        assert result["status_reason_code"] == "dev_mode_only"
    assert dev_supervisor.read_requests(control_dir) == []
