"""Dev bridge contract: dev context, restart and auto-restart (dev panel, #610)."""

from __future__ import annotations

import sys
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
    assert result["notice"] is None
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
        "active": False,
    }


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


def test_switch_returns_once_the_supervisor_accepted(
    worktrees: dict[str, Path], control_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    )
    supervisor.start()
    monkeypatch.setattr(dev_bridge.time, "sleep", lambda _seconds: supervisor.tick(0.0))

    assert CVMBridge().dev_switch_worktree({"path": str(worktrees["other"])}) == {"ok": True, "worktree": "wt-other"}
    assert supervisor.active_root == worktrees["other"]


def test_switch_refuses_a_worktree_that_needs_its_own_dependencies(
    worktrees: dict[str, Path], control_dir: Path
) -> None:
    result = CVMBridge().dev_switch_worktree({"path": str(worktrees["deps"])})

    assert result["ok"] is False
    assert "wt-deps needs its own dependencies (requirements.txt differ)" in result["error"]
    assert "supported in a later version" in result["error"]
    assert dev_supervisor.read_requests(control_dir) == []


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
