"""Agent command for the open dev mode window (#613): `status` and `switch` against a fake dev mode.

The fake dev mode is a real `DevSupervisor` on a real control directory, registered
the way `dev_supervisor.run` registers it, with fake apps and a fake clock: no
process, no window, no git.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable
from unittest.mock import Mock

import pytest

from desktop import dev_control, dev_data, dev_supervisor, lockfile
from desktop.dev_bootstrap import BootstrapError

_real_sleep = time.sleep


def _row(path: Path, branch: str, differences: list[str] | None = None) -> dict[str, object]:
    """A `dev_data.list_worktrees` row; the differing manifests are not installed yet."""
    return {
        "name": path.name,
        "path": str(path),
        "branch": branch,
        "is_main_checkout": path.name == "analisys",
        "isolated_data": False,
        "dependency_differences": differences or [],
        "installs_needed": differences or [],
    }


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """A main checkout and three linked worktrees, laid out as git lays them out.

    The command runs from `wt-613`; `wt-deps` needs its own dependencies.
    """
    main = tmp_path / "analisys"
    (main / ".git").mkdir(parents=True)
    roots = {"main": main, "here": tmp_path / "wt-613", "other": tmp_path / "wt-other", "deps": tmp_path / "wt-deps"}
    for root in list(roots.values())[1:]:
        git_dir = main / ".git" / "worktrees" / root.name
        git_dir.mkdir(parents=True)
        (git_dir / "commondir").write_text("../..\n", encoding="utf-8")
        root.mkdir()
        (root / ".git").write_text(f"gitdir: {git_dir}\n", encoding="utf-8")
    rows = [
        _row(main, "main"),
        _row(roots["here"], "feat/613-agent-switch-command"),
        _row(roots["other"], "feat/other"),
        _row(roots["deps"], "feat/deps", ["requirements.txt"]),
    ]
    monkeypatch.setattr(dev_data, "list_worktrees", lambda _root, env_root: [dict(row) for row in rows])
    for name in ("CVM_DATA_DIR", "CVMANALYTICS_USE_RELEASE_DATA"):
        monkeypatch.delenv(name, raising=False)
    return roots


class FakeDevMode:
    """Dev mode launched from the main checkout. Each sleep of the command is one supervisor tick, 10 s later.

    `apps` are the fake apps started so far; `on_tick` runs before each tick.
    """

    def __init__(
        self,
        repo: dict[str, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        provision: Callable[[Path, list[str], Callable[[str], None]], None] | None = None,
    ) -> None:
        self.control_dir = tmp_path / "control"
        self.control_dir.mkdir()
        self.apps: list[Mock] = []
        self.now = 0.0
        self.on_tick: Callable[[FakeDevMode], None] | None = None
        self.supervisor = dev_supervisor.DevSupervisor(
            start_child=self._start,
            stop_child=lambda _app: True,
            scan=dict,
            report=lambda _message: None,
            read_requests=lambda: dev_supervisor.read_requests(self.control_dir),
            publish_status=lambda status: dev_supervisor.write_status(self.control_dir, status),
            list_worktrees=lambda: dev_data.list_worktrees(repo["main"], env_root=repo["main"]),
            launch_root=repo["main"],
            provision=provision,
        )
        self.supervisor.start()
        self.record = dev_supervisor.register(repo["main"], self.control_dir)
        assert self.record is not None
        monkeypatch.setattr(dev_control.time, "sleep", self._tick)

    def _start(self) -> Mock:
        app = Mock(**{"poll.return_value": None})
        self.apps.append(app)
        return app

    def _tick(self, _seconds: float) -> None:
        _real_sleep(0.001)  # lets an install thread run
        self.now += 10.0
        if self.on_tick:
            self.on_tick(self)
        self.supervisor.tick(self.now)

    def switch_now(self, root: Path) -> None:
        dev_supervisor.send_request(self.control_dir, "switch_worktree", path=str(root))
        self.supervisor.tick(self.now)


def _run(repo: dict[str, Path], capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = dev_control.main(list(argv), repo_root=repo["here"])
    out, err = capsys.readouterr()
    return code, out, err


# --- status ---------------------------------------------------------------------


def test_status_reports_the_worktree_branch_and_data_mode_of_the_window(
    repo: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dev = FakeDevMode(repo, tmp_path, monkeypatch)

    code, out, err = _run(repo, capsys, "status")

    assert (code, err) == (0, "")
    assert out.splitlines() == [
        f"Dev mode: running (supervisor PID {dev_supervisor.os.getpid()}, launched from {repo['main']})",
        f"Active worktree: analisys ({repo['main']})",
        "This checkout: wt-613, not the active worktree",
        "Branch: main",
        f"Data mode: shared ({repo['main'] / 'data' / 'dev-runtime'})",
        "Switch in progress: no",
        "Install in progress: no",
    ]


def test_status_reports_an_isolated_worktree_and_a_switch_still_in_its_grace_period(
    repo: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo["here"] / dev_data.MARKER_NAME).write_text("isolated\n", encoding="utf-8")
    dev = FakeDevMode(repo, tmp_path, monkeypatch)
    dev.switch_now(repo["here"])

    code, out, _err = _run(repo, capsys, "status")

    assert code == 0
    assert f"Active worktree: wt-613 ({repo['here']})" in out
    assert "This checkout: wt-613, the active worktree" in out
    assert "Branch: feat/613-agent-switch-command" in out
    assert f"Data mode: isolated ({repo['here'] / 'data' / 'dev-runtime'})" in out
    assert "Switch in progress: yes, from analisys; confirmed once the app has run 60 seconds" in out


@pytest.mark.parametrize(
    ("variable", "value", "expected"),
    [
        ("CVM_DATA_DIR", "scratch", "Data mode: custom ("),
        ("CVMANALYTICS_USE_RELEASE_DATA", "1", "Data mode: installed-app"),
    ],
)
def test_status_reports_the_data_path_overrides_dev_mode_was_started_with(
    repo: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    variable: str,
    value: str,
    expected: str,
) -> None:
    monkeypatch.setenv(variable, str(tmp_path / value) if value == "scratch" else value)
    FakeDevMode(repo, tmp_path, monkeypatch)

    code, out, _err = _run(repo, capsys, "status")

    assert code == 0
    assert expected in out


# --- switch ---------------------------------------------------------------------


def test_switch_without_a_target_switches_to_the_checkout_it_runs_from(
    repo: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dev = FakeDevMode(repo, tmp_path, monkeypatch)

    code, out, err = _run(repo, capsys, "switch")

    assert (code, err) == (0, "")
    lines = out.splitlines()
    assert lines[0] == "Asked dev mode to switch the window to wt-613."
    assert lines[1].startswith("The window is reopening on wt-613. Waiting until the app has run 60 seconds")
    assert lines[-1] == "The window runs wt-613."
    assert dev.supervisor.active_root == repo["here"]
    assert dev.now > dev_supervisor.SWITCH_GRACE_SECONDS, "it waits until a crash can no longer return the window"


@pytest.mark.parametrize("target", ["path", "wt-other", "feat/other"])
def test_switch_finds_the_worktree_by_path_folder_name_or_branch(
    repo: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    target: str,
) -> None:
    dev = FakeDevMode(repo, tmp_path, monkeypatch)

    code, out, _err = _run(repo, capsys, "switch", str(repo["other"]) if target == "path" else target)

    assert code == 0
    assert out.splitlines()[-1] == "The window runs wt-other."
    assert dev.supervisor.active_root == repo["other"]


def test_switch_to_the_worktree_the_window_already_runs_sends_nothing(
    repo: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dev = FakeDevMode(repo, tmp_path, monkeypatch)

    code, out, _err = _run(repo, capsys, "switch", "main")

    assert (code, out) == (0, "The window already runs analisys.\n")
    assert len(dev.apps) == 1
    assert dev_supervisor.read_requests(dev.control_dir) == []


def test_switch_prints_the_install_progress_then_switches(
    repo: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    released = threading.Event()

    def provision(_root: Path, _manifests: list[str], progress: Callable[[str], None]) -> None:
        progress("Creating Python environment")
        assert released.wait(5), "the test never released the install"

    dev = FakeDevMode(repo, tmp_path, monkeypatch, provision)
    dev.on_tick = lambda d: released.set() if d.now >= 50 else None

    code, out, err = _run(repo, capsys, "switch", "wt-deps")

    assert (code, err) == (0, "")
    assert "Installing dependencies for wt-deps: Creating Python environment..." in out.splitlines()
    assert out.splitlines()[-1] == "The window runs wt-deps."
    assert dev.supervisor.active_root == repo["deps"]


def test_failed_install_fails_the_switch_with_the_command_and_its_output(
    repo: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def provision(_root: Path, _manifests: list[str], progress: Callable[[str], None]) -> None:
        progress("Installing Python packages")
        raise BootstrapError(["python", "-m", "pip", "install"], 1, "ERROR: No matching distribution found for nope\n")

    dev = FakeDevMode(repo, tmp_path, monkeypatch, provision)

    code, _out, err = _run(repo, capsys, "switch", "wt-deps")

    assert code == 1
    assert err.splitlines() == [
        "error: Installing dependencies for wt-deps failed; the window stays on analisys.",
        "Command: python -m pip install (exit code 1)",
        "ERROR: No matching distribution found for nope",
    ]
    assert dev.supervisor.active_root == repo["main"]


def test_app_that_fails_on_the_worktree_fails_the_switch_and_the_window_returns(
    repo: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dev = FakeDevMode(repo, tmp_path, monkeypatch)

    def crash_the_switched_to_app(d: FakeDevMode) -> None:
        if len(d.apps) == 2:
            d.apps[1].poll.return_value = 1

    dev.on_tick = crash_the_switched_to_app

    code, out, err = _run(repo, capsys, "switch", "wt-other")

    assert code == 1
    assert "The window is reopening on wt-other" in out
    assert "error: Switching to wt-other failed: the app exited with code 1" in err
    assert "The window is back on analisys." in err
    assert dev.supervisor.active_root == repo["main"]


def test_unknown_target_is_refused_without_a_request(
    repo: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dev = FakeDevMode(repo, tmp_path, monkeypatch)

    code, out, err = _run(repo, capsys, "switch", "no-such-worktree")

    assert (code, out) == (1, "")
    assert "error: no-such-worktree is not a worktree of this repository. Worktrees:" in err
    assert f"wt-other (feat/other): {repo['other']}" in err
    assert dev_supervisor.read_requests(dev.control_dir) == []


def test_switch_fails_when_the_supervisor_does_not_confirm(
    repo: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    FakeDevMode(repo, tmp_path, monkeypatch)
    monkeypatch.setattr(dev_control.time, "sleep", lambda _seconds: None)  # the supervisor never polls
    monkeypatch.setattr(dev_control, "CONFIRM_TIMEOUT_SECONDS", 0.0)

    code, _out, err = _run(repo, capsys, "switch", "wt-other")

    assert (code, err) == (1, "error: The dev supervisor did not confirm the switch.\n")


def test_switch_fails_when_dev_mode_ends_before_it_is_done(
    repo: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dev = FakeDevMode(repo, tmp_path, monkeypatch)
    monkeypatch.setattr(dev_control.time, "sleep", lambda _seconds: dev_supervisor.shutil.rmtree(dev.control_dir))

    code, _out, err = _run(repo, capsys, "switch", "wt-other")

    assert (code, err) == (1, "error: Dev mode ended before the window switched to wt-other.\n")


# --- finding dev mode -----------------------------------------------------------


@pytest.mark.parametrize("command", ["status", "switch"])
def test_without_dev_mode_both_commands_fail_plainly(
    repo: dict[str, Path], capsys: pytest.CaptureFixture[str], command: str
) -> None:
    code, out, err = _run(repo, capsys, command)

    assert (code, out) == (1, "")
    assert err.startswith("error: No dev mode is running for this repository;")
    assert "python -m desktop.app --dev" in err


@pytest.mark.parametrize("gone", ["process", "control directory"])
def test_a_stale_record_is_reported_and_removed(
    repo: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    gone: str,
) -> None:
    dev = FakeDevMode(repo, tmp_path, monkeypatch)
    if gone == "process":
        monkeypatch.setattr(lockfile, "_pid_alive", lambda _pid: False)
        reason = "is no longer running"
    else:
        dev_supervisor.shutil.rmtree(dev.control_dir)
        reason = "control directory of the dev supervisor launched from"

    code, _out, err = _run(repo, capsys, "switch")

    assert code == 1
    assert err.startswith("error: No dev mode is running for this repository;")
    assert "Removed a stale record:" in err and reason in err
    assert not dev.record.exists()


def test_several_dev_modes_need_a_pid_to_switch(
    repo: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dev = FakeDevMode(repo, tmp_path, monkeypatch)
    other = json.loads(dev.record.read_text(encoding="utf-8")) | {"pid": 4, "launch_root": str(repo["other"])}
    (dev.record.parent / "4.json").write_text(json.dumps(other), encoding="utf-8")
    monkeypatch.setattr(lockfile, "_pid_alive", lambda _pid: True)

    code, _out, err = _run(repo, capsys, "switch")
    assert code == 1
    assert "Several dev mode windows are running; choose one:" in err
    assert f"--pid 4: launched from {repo['other']}" in err

    code, out, _err = _run(repo, capsys, "status")
    assert code == 0
    assert out.count("Dev mode: running") == 2

    code, out, _err = _run(repo, capsys, "--pid", str(dev_supervisor.os.getpid()), "switch")
    assert code == 0
    assert dev.supervisor.active_root == repo["here"]
