"""Dev bridge contract: dev context, restart, auto-restart (#610), worktree switch (#611) and dev data actions (#614)."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from desktop import dev_bootstrap, dev_data, dev_supervisor
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


@pytest.mark.parametrize("git_read", [dev_bridge._git_status, dev_data._git_worktree_list])
def test_git_reads_do_not_inherit_the_supervisor_stop_pipe(git_read, tmp_path, monkeypatch):
    run = Mock()
    monkeypatch.setattr(subprocess, "run", run)
    git_read(tmp_path)
    assert run.call_args.kwargs.get("stdin") == subprocess.DEVNULL


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
        stop_child=lambda _child: True,
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


# --- dev_list_worktrees / dev_switch_worktree (#611) ---------------------------


def _write_manifests(checkout: Path, requirements: str = "pywebview\n") -> None:
    (checkout / "apps" / "desktop-web").mkdir(parents=True, exist_ok=True)
    (checkout / "requirements.txt").write_text(requirements, encoding="utf-8")
    (checkout / "apps" / "desktop-web" / "package-lock.json").write_text("{}\n", encoding="utf-8")
    (checkout / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")


def _install_environment(checkout: Path) -> None:
    dev_bootstrap.write_python_stamp(checkout, dev_bootstrap.python_stamp(checkout, "python"))
    dev_bootstrap.write_frontend_stamp(checkout)


@pytest.fixture
def worktrees(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """The window runs `wt-610`; the main checkout has the installed environment.

    `wt-other` has the same dependencies, `wt-deps` a different requirements.txt.
    """
    roots = {
        "main": checkout.parent / "main",
        "window": checkout,
        "other": checkout.parent / "wt-other",
        "deps": checkout.parent / "wt-deps",
    }
    for root in roots.values():
        _write_manifests(root)
    _write_manifests(roots["deps"], requirements="pywebview\nnew-package\n")
    _install_environment(roots["main"])
    porcelain = "".join(f"worktree {root.as_posix()}\nHEAD 1\ndetached\n\n" for root in roots.values())
    monkeypatch.setattr(dev_data, "_git_worktree_list", lambda _root: porcelain)
    monkeypatch.delenv(dev_supervisor.LAUNCH_ROOT_ENV, raising=False)
    return roots


def test_worktree_list_marks_the_window_and_flags_different_dependencies(
    worktrees: dict[str, Path], control_dir: Path
) -> None:
    result = CVMBridge().dev_list_worktrees()

    assert result["ok"] is True
    assert result["supervised"] is True
    assert (result["notice"], result["notice_detail"], result["install"]) == (None, None, None)
    rows = [(w["name"], w["is_main_checkout"], w["active"], w["dependency_differences"]) for w in result["worktrees"]]
    assert rows == [
        ("main", True, False, []),
        ("wt-610", False, True, []),
        ("wt-other", False, False, []),
        ("wt-deps", False, False, ["requirements.txt"]),
    ]
    assert result["worktrees"][2] == {
        "name": "wt-other",
        "path": str(worktrees["other"]),
        "branch": None,
        "is_main_checkout": False,
        "isolated_data": False,
        "dependency_differences": [],
        "installs_needed": [],
        "active": False,
    }
    assert result["worktrees"][3]["installs_needed"] == ["requirements.txt"]


def test_worktree_list_compares_with_the_environment_dev_mode_was_launched_with(
    worktrees: dict[str, Path], control_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_environment(worktrees["deps"])
    monkeypatch.setenv(dev_supervisor.LAUNCH_ROOT_ENV, str(worktrees["deps"]))

    differences = {w["name"]: w["dependency_differences"] for w in CVMBridge().dev_list_worktrees()["worktrees"]}

    assert differences == {"main": ["requirements.txt"], "wt-610": ["requirements.txt"],
                           "wt-other": ["requirements.txt"], "wt-deps": []}


def test_worktree_list_shows_why_the_last_switch_did_not_happen(worktrees: dict[str, Path], control_dir: Path) -> None:
    notice = "Worktree wt-other was removed; the window is back on main."
    dev_supervisor.write_status(control_dir, {"auto_restart": True, "pending_changes": 0, "worktree_notice": notice})

    assert CVMBridge().dev_list_worktrees()["notice"] == notice


def test_worktree_list_without_a_supervisor_or_git(worktrees: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    assert CVMBridge().dev_list_worktrees()["supervised"] is False

    def git_fails(_root: Path) -> str:
        raise dev_bridge.subprocess.CalledProcessError(128, "git worktree list")

    monkeypatch.setattr(dev_data, "_git_worktree_list", git_fails)
    result = CVMBridge().dev_list_worktrees()
    assert result["ok"] is False
    assert "git worktree list" in result["error"]


def _real_supervisor(
    worktrees: dict[str, Path], control_dir: Path, provision: object = None
) -> dev_supervisor.DevSupervisor:
    """A dev supervisor on the control directory, launched from the main checkout; no process."""
    main = worktrees["main"]
    supervisor = dev_supervisor.DevSupervisor(
        start_child=lambda: Mock(**{"poll.return_value": None}),
        stop_child=lambda _child: True,
        scan=dict,
        report=lambda _message: None,
        read_requests=lambda: dev_supervisor.read_requests(control_dir),
        publish_status=lambda status: dev_supervisor.write_status(control_dir, status),
        list_worktrees=lambda: dev_data.list_worktrees(main, env_root=main),
        launch_root=main,
        provision=provision,
    )
    supervisor.start()
    return supervisor


def test_switch_returns_once_the_supervisor_accepted(
    worktrees: dict[str, Path], control_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    supervisor = _real_supervisor(worktrees, control_dir)
    monkeypatch.setattr(dev_bridge.time, "sleep", lambda _seconds: supervisor.tick(0.0))

    assert CVMBridge().dev_switch_worktree({"path": str(worktrees["other"])}) == {
        "ok": True,
        "worktree": "wt-other",
        "installing": False,
    }
    assert supervisor.active_root == worktrees["other"]


def test_switch_to_a_worktree_with_other_dependencies_returns_once_its_install_started(
    worktrees: dict[str, Path], control_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    released = threading.Event()

    def provision(_root: Path, _manifests: list[str], progress) -> None:
        progress("Installing Python packages")
        released.wait(5)

    supervisor = _real_supervisor(worktrees, control_dir, provision)
    monkeypatch.setattr(dev_bridge.time, "sleep", lambda _seconds: supervisor.tick(0.0))

    assert CVMBridge().dev_switch_worktree({"path": str(worktrees["deps"])}) == {
        "ok": True,
        "worktree": "wt-deps",
        "installing": True,
    }
    assert supervisor.active_root == worktrees["main"], "the window stays where it is during the install"
    install = CVMBridge().dev_list_worktrees()["install"]
    assert (install["name"], install["worktree"]) == ("wt-deps", str(worktrees["deps"]))
    assert isinstance(install["step"], str) and isinstance(install["started_at"], float)

    refused = CVMBridge().dev_switch_worktree({"path": str(worktrees["other"])})
    assert refused == {"ok": False, "error": "Dependencies for wt-deps are still installing; switch again once they are ready."}

    released.set()
    deadline = time.monotonic() + 5
    while supervisor.active_root != worktrees["deps"]:
        assert time.monotonic() < deadline, "the supervisor did not switch after the install"
        supervisor.tick(1.0)
    assert CVMBridge().dev_list_worktrees()["install"] is None


def test_worktree_list_shows_the_command_of_a_failed_install(worktrees: dict[str, Path], control_dir: Path) -> None:
    notice = "Installing dependencies for wt-deps failed; the window stays on main."
    detail = {"command": "npm.cmd ci", "exit_code": 1, "output": "npm ERR! code ETARGET"}
    dev_supervisor.write_status(control_dir, {"worktree_notice": notice, "worktree_notice_detail": detail, "install": None})

    result = CVMBridge().dev_list_worktrees()

    assert (result["notice"], result["notice_detail"], result["install"]) == (notice, detail, None)


@pytest.mark.parametrize(
    ("params", "message"),
    [
        (None, "`path`"),
        ({"path": 3}, "`path`"),
        ({"path": "C:/nowhere"}, "not a worktree of this repository"),
        ("window", "already runs wt-610"),
    ],
)
def test_switch_refuses_what_is_not_another_worktree(
    worktrees: dict[str, Path], control_dir: Path, params: object, message: str
) -> None:
    if params == "window":
        params = {"path": str(worktrees["window"])}

    result = CVMBridge().dev_switch_worktree(params)

    assert result["ok"] is False
    assert message in result["error"]
    assert dev_supervisor.read_requests(control_dir) == []


def test_switch_reports_a_refusal_from_the_supervisor(
    worktrees: dict[str, Path], control_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    refusal = "wt-other is not a worktree of this repository (it may have been removed)."

    def supervisor_refuses(_seconds: float) -> None:
        dev_supervisor.write_status(control_dir, {"worktree": str(worktrees["window"]), "worktree_notice": refusal})

    monkeypatch.setattr(dev_bridge.time, "sleep", supervisor_refuses)

    assert CVMBridge().dev_switch_worktree({"path": str(worktrees["other"])}) == {"ok": False, "error": refusal}


def test_switch_fails_plainly_without_a_supervisor_or_its_confirmation(
    worktrees: dict[str, Path], control_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dev_bridge.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(dev_bridge, "CONFIRM_TIMEOUT_SECONDS", 0.0)
    result = CVMBridge().dev_switch_worktree({"path": str(worktrees["other"])})
    assert result == {"ok": False, "error": "The dev supervisor did not confirm the switch."}

    monkeypatch.delenv(dev_supervisor.CONTROL_DIR_ENV)
    result = CVMBridge().dev_switch_worktree({"path": str(worktrees["other"])})
    assert result["ok"] is False
    assert "supervisor is not running" in result["error"]


def test_worktree_methods_refuse_in_the_packaged_app(
    worktrees: dict[str, Path], control_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(dev_data, "_git_worktree_list", lambda _root: pytest.fail("the packaged app must not run git"))
    bridge = CVMBridge()

    for result in (bridge.dev_list_worktrees(), bridge.dev_switch_worktree({"path": str(worktrees["other"])})):
        assert result["ok"] is False
        assert result["status"] == "blocked"
        assert result["status_reason_code"] == "dev_mode_only"
    assert dev_supervisor.read_requests(control_dir) == []


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


def test_data_action_of_a_window_on_an_isolated_worktree_targets_that_worktree(
    shared_data: Path, checkout: Path, control_dir: Path
) -> None:
    """After a worktree switch the window runs that worktree's code, so its data is the one acted on."""
    (checkout / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    (checkout / dev_data.MARKER_NAME).write_text("isolated\n", encoding="utf-8")
    (checkout / "data" / "dev-runtime" / "db").mkdir(parents=True)

    assert CVMBridge().dev_move_data_to_backup({"target": "db"}) == {"ok": True}

    request = dev_supervisor.read_requests(control_dir)[0]
    assert (request["mode"], request["data_root"], request["shared_root"]) == (
        "isolated", str(checkout / "data" / "dev-runtime"), str(shared_data))


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
