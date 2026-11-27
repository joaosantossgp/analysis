from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from desktop import dev_supervisor as sup


class FakeChild:
    def __init__(self) -> None:
        self.exit_code: int | None = None

    def poll(self) -> int | None:
        return self.exit_code


class Harness:
    """A supervisor wired to fakes: no process, no window, no real clock."""

    def __init__(self) -> None:
        self.snapshot: dict[str, tuple[int, int]] = {"desktop/app.py": (1, 10)}
        self.started: list[FakeChild] = []
        self.stopped: list[FakeChild] = []
        self.messages: list[str] = []
        self.requests: list[dict[str, object]] = []
        self.queued_while_stopping: list[dict[str, object]] = []
        self.statuses: list[dict[str, object]] = []
        self.child_exits_on_stop = True
        self.start_error: OSError | None = None
        # (request, apps started so far, apps stopped so far) at the moment each data action ran.
        self.data_actions: list[tuple[dict[str, object], int, int]] = []
        self.data_action_error: Exception | None = None
        self.supervisor = sup.DevSupervisor(
            start_child=self._start,
            stop_child=self._stop,
            scan=lambda: dict(self.snapshot),
            report=self.messages.append,
            quiet_seconds=1.0,
            read_requests=self._take_requests,
            publish_status=self.statuses.append,
            run_data_action=self._run_data_action,
        )
        self.supervisor.start()

    def _run_data_action(self, request: dict[str, object]) -> str:
        self.data_actions.append((request, len(self.started), len(self.stopped)))
        if self.data_action_error is not None:
            raise self.data_action_error
        return f"Moved {request['target']} to backup."

    def _stop(self, child: FakeChild) -> bool:
        self.stopped.append(child)
        self.requests += self.queued_while_stopping
        return self.child_exits_on_stop

    def _take_requests(self) -> list[dict[str, object]]:
        taken, self.requests = self.requests, []
        return taken

    def _start(self) -> FakeChild:
        if self.start_error is not None:
            error, self.start_error = self.start_error, None
            raise error
        child = FakeChild()
        self.started.append(child)
        return child

    def save(self, name: str = "desktop/app.py") -> None:
        mtime, size = self.snapshot.get(name, (0, 0))
        self.snapshot[name] = (mtime + 1, size)


def test_supervises_only_dev_launches_that_are_not_already_children() -> None:
    assert sup.should_supervise(["--dev"], {}) is True
    assert sup.should_supervise(["--dev", "--debug"], {}) is True
    assert sup.should_supervise([], {}) is False
    assert sup.should_supervise(["--vite"], {}) is False
    assert sup.should_supervise(["--dev"], {sup.STATE_FILE_ENV: "x.json"}) is False


def test_scan_sources_tracks_python_files_of_the_desktop_shell_and_core(tmp_path: Path) -> None:
    for name in ("desktop/app.py", "src/core/calc.py", "desktop/__pycache__/app.py", "desktop/notes.txt",
                 "apps/api/main.py", "src/.hidden/x.py"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n", encoding="utf-8")

    before = sup.scan_sources(tmp_path)
    assert sorted(before) == ["desktop/app.py", "src/core/calc.py"]

    (tmp_path / "src/core/calc.py").write_text("x = 22222\n", encoding="utf-8")
    edited = sup.scan_sources(tmp_path)
    assert edited["src/core/calc.py"] != before["src/core/calc.py"]
    assert edited["desktop/app.py"] == before["desktop/app.py"]

    (tmp_path / "desktop/new_module.py").write_text("", encoding="utf-8")
    (tmp_path / "desktop/app.py").unlink()
    assert sorted(sup.scan_sources(tmp_path)) == ["desktop/new_module.py", "src/core/calc.py"]


def test_scan_sources_tolerates_a_missing_watched_directory(tmp_path: Path) -> None:
    assert sup.scan_sources(tmp_path) == {}


def test_no_change_never_restarts() -> None:
    h = Harness()

    for now in (0.0, 5.0, 60.0):
        assert h.supervisor.tick(now) is None

    assert len(h.started) == 1
    assert h.stopped == []


def test_burst_of_saves_causes_one_restart_after_the_quiet_period() -> None:
    h = Harness()

    h.save("desktop/app.py")
    assert h.supervisor.tick(0.0) is None
    h.save("src/core/calc.py")
    assert h.supervisor.tick(0.4) is None
    h.save("desktop/app.py")
    assert h.supervisor.tick(0.8) is None
    assert len(h.started) == 1, "still inside the quiet period of the last save"

    assert h.supervisor.tick(1.7) is None
    assert h.supervisor.tick(1.9) is None
    assert h.supervisor.tick(30.0) is None

    assert len(h.started) == 2
    assert h.stopped == [h.started[0]]


def test_restart_message_names_the_changed_files() -> None:
    h = Harness()

    h.save("desktop/app.py")
    h.supervisor.tick(0.0)
    h.supervisor.tick(2.0)

    assert any("desktop/app.py" in message for message in h.messages)


def test_window_closed_by_the_user_ends_dev_mode_even_with_a_pending_change() -> None:
    h = Harness()

    h.save()
    assert h.supervisor.tick(0.0) is None
    h.started[0].exit_code = 0

    assert h.supervisor.tick(5.0) == 0
    assert len(h.started) == 1
    assert h.stopped == []


def test_failed_start_keeps_dev_mode_alive_and_retries_on_the_next_change() -> None:
    h = Harness()
    h.started[0].exit_code = 1

    assert h.supervisor.tick(0.0) is None
    assert h.supervisor.tick(10.0) is None
    failures = [message for message in h.messages if "exit code 1" in message]
    assert len(failures) == 1, "the failure is reported once, not on every poll"
    assert len(h.started) == 1

    h.save()
    assert h.supervisor.tick(20.0) is None
    assert h.supervisor.tick(21.5) is None

    assert len(h.started) == 2
    assert h.stopped == [], "there is no running child to stop after a failed start"


def test_shutdown_stops_a_running_child_only() -> None:
    h = Harness()
    h.supervisor.shutdown()
    assert h.stopped == [h.started[0]]

    failed = Harness()
    failed.started[0].exit_code = 1
    failed.supervisor.tick(0.0)
    failed.supervisor.shutdown()
    assert failed.stopped == []


def test_stop_child_closes_stdin_and_waits_for_a_clean_exit() -> None:
    proc = Mock(pid=4242)

    with patch.object(sup.subprocess, "run") as run:
        assert sup.stop_child(proc) is True

    proc.stdin.close.assert_called_once_with()
    proc.wait.assert_called_once_with(timeout=sup.STOP_TIMEOUT_SECONDS)
    run.assert_not_called()
    proc.kill.assert_not_called()


def test_stop_child_kills_the_process_tree_when_the_child_does_not_exit() -> None:
    proc = Mock(pid=4242)
    proc.wait.side_effect = [subprocess.TimeoutExpired("app", sup.STOP_TIMEOUT_SECONDS), 1]

    with patch.object(sup.subprocess, "run") as run, patch.object(sup.os, "name", "nt"):
        assert sup.stop_child(proc) is True

    run.assert_called_once_with(
        ["taskkill", "/PID", "4242", "/T", "/F"],
        check=False,
        timeout=sup.STOP_TIMEOUT_SECONDS,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_stop_child_survives_a_taskkill_timeout_and_reports_whether_the_child_exited() -> None:
    timeout = subprocess.TimeoutExpired("x", sup.STOP_TIMEOUT_SECONDS)
    hung_taskkill = patch.object(sup.subprocess, "run", side_effect=subprocess.TimeoutExpired("taskkill", 10))

    exited = Mock(pid=4242)
    exited.wait.side_effect = [timeout, 1]
    with hung_taskkill, patch.object(sup.os, "name", "nt"):
        assert sup.stop_child(exited) is True

    alive = Mock(pid=4242)
    alive.wait.side_effect = [timeout, timeout]
    with hung_taskkill, patch.object(sup.os, "name", "nt"):
        assert sup.stop_child(alive) is False


def test_child_that_survives_the_stop_gets_no_replacement_until_it_is_gone() -> None:
    h = Harness()
    h.child_exits_on_stop = False

    h.requests.append({"action": "restart"})
    assert h.supervisor.tick(0.0) is None

    assert len(h.started) == 1, "no second app while the first still holds the lock and port"
    assert any("did not stop" in message for message in h.messages)

    assert h.supervisor.tick(1.0) is None
    assert h.stopped == [h.started[0], h.started[0]], "the stop is retried on the next poll"
    assert len(h.started) == 1

    h.child_exits_on_stop = True
    assert h.supervisor.tick(2.0) is None
    assert len(h.started) == 2
    assert h.supervisor.tick(3.0) is None
    assert len(h.started) == 2, "one replacement only"


def test_child_that_exits_late_after_a_failed_stop_is_replaced_and_does_not_end_dev_mode() -> None:
    h = Harness()
    h.child_exits_on_stop = False
    h.requests.append({"action": "restart"})
    h.supervisor.tick(0.0)

    h.started[0].exit_code = 0  # the stop request was honoured late

    assert h.supervisor.tick(1.0) is None
    assert len(h.started) == 2
    assert len(h.stopped) == 1, "an exited app is not stopped again"


def test_failed_spawn_on_a_restart_request_keeps_dev_mode_running() -> None:
    h = Harness()
    h.start_error = OSError("no such interpreter")

    h.requests.append({"action": "restart"})
    assert h.supervisor.tick(0.0) is None

    assert len(h.started) == 1
    assert any("Could not start the app" in message and "no such interpreter" in message for message in h.messages)
    assert h.supervisor.tick(5.0) is None
    assert len(h.started) == 1, "no retry loop without a change or a request"

    h.requests.append({"action": "restart"})
    assert h.supervisor.tick(6.0) is None
    assert len(h.started) == 2
    assert h.stopped == [h.started[0]], "there was no child to stop after the failed spawn"


def test_run_spawns_the_app_as_a_marked_child_and_returns_its_exit_code(tmp_path: Path) -> None:
    spawned: list[dict[str, object]] = []

    class ClosedWindowChild:
        stdin = Mock()

        def poll(self) -> int:
            return 0

    def fake_popen(command: list[str], **kwargs: object) -> ClosedWindowChild:
        spawned.append({"command": command, **kwargs})
        return ClosedWindowChild()

    with patch.object(sup.subprocess, "Popen", fake_popen), patch.object(sup.time, "sleep"):
        assert sup.run(["--dev", "--debug"], repo_root=tmp_path) == 0

    assert len(spawned) == 1
    assert spawned[0]["command"] == [sup.sys.executable, "-m", "desktop.app", "--dev", "--debug"]
    assert spawned[0]["cwd"] == str(tmp_path)
    assert spawned[0]["stdin"] == subprocess.PIPE
    state_file = Path(spawned[0]["env"][sup.STATE_FILE_ENV])  # type: ignore[index]
    assert not state_file.exists(), "the state file is removed when dev mode ends"
    assert sup.STATE_FILE_ENV not in os.environ


class FakeWindow:
    def __init__(self, route: object = "/#/empresas/4170", geometry: tuple[int, int, int, int] = (40, 60, 1400, 900)) -> None:
        self.route = route
        self.x, self.y, self.width, self.height = geometry

    def evaluate_js(self, _script: str) -> object:
        if isinstance(self.route, Exception):
            raise self.route
        return self.route


def test_window_state_round_trips_route_and_geometry(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"

    sup.save_window_state(state_file, FakeWindow())

    assert sup.load_window_state(state_file) == (
        "/#/empresas/4170",
        {"x": 40, "y": 60, "width": 1400, "height": 900},
    )


def test_missing_or_unusable_window_state_falls_back_to_defaults(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    assert sup.load_window_state(state_file) == ("", {})

    for content in ("not json", "[1, 2]", '{"route": 7, "geometry": {"x": "left"}}',
                    '{"route": "http://evil.example/", "geometry": {"x": 1, "y": 2, "width": 3}}'):
        state_file.write_text(content, encoding="utf-8")
        assert sup.load_window_state(state_file) == ("", {})


def test_minimized_window_keeps_the_previous_geometry(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    sup.save_window_state(state_file, FakeWindow())

    sup.save_window_state(state_file, FakeWindow(route="/#/setores", geometry=(-32000, -32000, 160, 28)))

    assert sup.load_window_state(state_file) == (
        "/#/setores",
        {"x": 40, "y": 60, "width": 1400, "height": 900},
    )


def test_unreadable_route_keeps_the_previous_route(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    sup.save_window_state(state_file, FakeWindow())

    sup.save_window_state(state_file, FakeWindow(route=RuntimeError("page not loaded"), geometry=(1, 2, 900, 700)))

    assert sup.load_window_state(state_file) == (
        "/#/empresas/4170",
        {"x": 1, "y": 2, "width": 900, "height": 700},
    )


def test_stop_request_saves_the_window_state_before_closing_the_windows(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    events: list[str] = []

    def close_windows() -> None:
        events.append(f"closed with state saved: {state_file.exists()}")

    thread = sup.watch_for_stop(state_file, FakeWindow(), close_windows, read=lambda: b"")
    thread.join(timeout=5)

    assert events == ["closed with state saved: True"]
    assert thread.daemon, "a blocked stdin read must not keep the app process alive"


def test_route_survives_when_no_geometry_was_ever_readable(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"

    sup.save_window_state(state_file, FakeWindow(route="/#/setores", geometry=(-32000, -32000, 160, 28)))

    assert sup.load_window_state(state_file) == ("/#/setores", {})


# --- Requests from the app (dev panel) ----------------------------------------


def test_restart_request_restarts_the_app_without_a_python_change() -> None:
    h = Harness()

    h.requests.append({"action": "restart"})
    assert h.supervisor.tick(0.0) is None
    assert h.supervisor.tick(5.0) is None

    assert len(h.started) == 2
    assert h.stopped == [h.started[0]]


def test_requests_queued_by_the_stopped_app_are_dropped() -> None:
    h = Harness()
    # A second click lands while the supervisor is stopping the app.
    h.queued_while_stopping = [{"action": "restart"}]

    h.requests.append({"action": "restart"})
    h.supervisor.tick(0.0)
    h.supervisor.tick(1.0)

    assert len(h.started) == 2, "one click burst, one restart"


def test_a_switch_change_sent_during_a_restart_is_still_applied() -> None:
    h = Harness()
    h.queued_while_stopping = [{"action": "set_auto_restart", "enabled": False}]

    h.requests.append({"action": "restart"})
    h.supervisor.tick(0.0)

    assert len(h.started) == 2
    assert h.statuses[-1] == {"auto_restart": False, "pending_changes": 0}


def test_auto_restart_off_holds_the_window_until_a_restart_is_requested() -> None:
    h = Harness()
    assert h.statuses[-1] == {"auto_restart": True, "pending_changes": 0}

    h.requests.append({"action": "set_auto_restart", "enabled": False})
    h.supervisor.tick(0.0)
    assert h.statuses[-1] == {"auto_restart": False, "pending_changes": 0}

    h.save("desktop/app.py")
    h.save("src/core/calc.py")
    h.supervisor.tick(1.0)
    h.supervisor.tick(60.0)
    assert len(h.started) == 1, "Python changes do not restart while auto-restart is off"
    assert h.statuses[-1] == {"auto_restart": False, "pending_changes": 2}

    h.requests.append({"action": "restart"})
    h.supervisor.tick(61.0)
    assert len(h.started) == 2
    assert h.statuses[-1] == {"auto_restart": False, "pending_changes": 0}


def test_turning_auto_restart_back_on_loads_the_changes_that_were_held() -> None:
    h = Harness()
    h.requests.append({"action": "set_auto_restart", "enabled": False})
    h.supervisor.tick(0.0)
    h.save()
    h.supervisor.tick(1.0)

    h.requests.append({"action": "set_auto_restart", "enabled": True})
    h.supervisor.tick(30.0)

    assert len(h.started) == 2
    assert h.statuses[-1] == {"auto_restart": True, "pending_changes": 0}


def test_auto_restart_off_still_recovers_from_a_failed_start() -> None:
    h = Harness()
    h.requests.append({"action": "set_auto_restart", "enabled": False})
    h.supervisor.tick(0.0)
    h.started[0].exit_code = 1
    h.supervisor.tick(1.0)

    h.save()
    h.supervisor.tick(2.0)
    h.supervisor.tick(4.0)

    assert len(h.started) == 2, "with no window there is no panel to restart from"


def test_unknown_or_malformed_requests_are_reported_and_ignored() -> None:
    h = Harness()

    h.requests += [{"action": "format_disk"}, {"action": "set_auto_restart", "enabled": "no"}, {}]
    assert h.supervisor.tick(0.0) is None

    assert len(h.started) == 1
    assert h.statuses[-1] == {"auto_restart": True, "pending_changes": 0}
    assert sum("ignored" in message.lower() for message in h.messages) == 3


def test_status_is_published_only_when_it_changes() -> None:
    h = Harness()

    for now in (0.0, 1.0, 2.0):
        h.supervisor.tick(now)

    assert h.statuses == [{"auto_restart": True, "pending_changes": 0}]


def test_request_files_reach_the_supervisor_oldest_first_and_only_once(tmp_path: Path) -> None:
    assert sup.read_requests(tmp_path) == []

    sup.send_request(tmp_path, "set_auto_restart", enabled=False)
    sup.send_request(tmp_path, "restart")
    (tmp_path / "requests" / "0-broken.json").write_text("not json", encoding="utf-8")
    (tmp_path / "requests" / "1-list.json").write_text("[1]", encoding="utf-8")

    messages: list[str] = []
    assert sup.read_requests(tmp_path, report=messages.append) == [
        {"action": "set_auto_restart", "enabled": False},
        {"action": "restart"},
    ]
    assert sup.read_requests(tmp_path) == []
    assert len(messages) == 2 and all("Ignored" in message for message in messages)


def test_oversized_or_deeply_nested_request_files_are_reported_and_ignored(tmp_path: Path) -> None:
    requests = tmp_path / "requests"
    requests.mkdir()
    padding = "x" * (sup.MAX_REQUEST_BYTES + 1)
    (requests / "0-big.json").write_text(f'{{"action": "restart", "pad": "{padding}"}}', encoding="utf-8")
    (requests / "1-deep.json").write_text("[" * 50_000, encoding="utf-8")
    sup.send_request(tmp_path, "restart")
    messages: list[str] = []

    assert sup.read_requests(tmp_path, report=messages.append) == [{"action": "restart"}]

    assert len(messages) == 2
    assert "0-big.json" in messages[0] and "64 KB" in messages[0]
    assert "1-deep.json" in messages[1] and "recursion" in messages[1]
    assert list(requests.iterdir()) == [], "bad requests are dropped, not retried"


def test_status_file_round_trips_and_a_missing_one_reads_as_empty(tmp_path: Path) -> None:
    assert sup.read_status(tmp_path) == {}

    sup.write_status(tmp_path, {"auto_restart": False, "pending_changes": 3})

    assert sup.read_status(tmp_path) == {"auto_restart": False, "pending_changes": 3}
    (tmp_path / "status.json").write_text("[]", encoding="utf-8")
    assert sup.read_status(tmp_path) == {}


def test_run_gives_the_app_a_control_directory_and_removes_it_afterwards(tmp_path: Path) -> None:
    control_dirs: list[Path] = []

    class ClosedWindowChild:
        stdin = Mock()

        def poll(self) -> int:
            return 0

    def fake_popen(_command: list[str], **kwargs: object) -> ClosedWindowChild:
        control_dir = Path(kwargs["env"][sup.CONTROL_DIR_ENV])  # type: ignore[index]
        assert sup.read_status(control_dir) == {"auto_restart": True, "pending_changes": 0}
        control_dirs.append(control_dir)
        return ClosedWindowChild()

    with patch.object(sup.subprocess, "Popen", fake_popen), patch.object(sup.time, "sleep"):
        assert sup.run(["--dev"], repo_root=tmp_path) == 0

    assert len(control_dirs) == 1
    assert not control_dirs[0].exists()


# --- Dev data actions (dev panel, #614) ----------------------------------------

DATA_ACTION = {"action": "data_action", "operation": "backup", "target": "db"}


def test_data_action_runs_with_the_app_stopped_then_the_app_starts_again() -> None:
    h = Harness()

    h.requests.append(DATA_ACTION)
    assert h.supervisor.tick(0.0) is None

    assert h.data_actions == [(DATA_ACTION, 1, 1)], "the app was stopped and not yet started again"
    assert h.stopped == [h.started[0]]
    assert len(h.started) == 2
    assert "[dev] Moved db to backup." in h.messages
    assert h.supervisor.tick(1.0) is None
    assert len(h.data_actions) == 1, "a data action runs once"


def test_data_action_waits_while_the_app_does_not_stop() -> None:
    h = Harness()
    h.child_exits_on_stop = False

    h.requests.append(DATA_ACTION)
    h.supervisor.tick(0.0)
    assert h.data_actions == [], "never touch data while the app may hold a database handle"

    h.child_exits_on_stop = True
    h.supervisor.tick(1.0)
    assert h.data_actions == [(DATA_ACTION, 1, 2)]
    assert len(h.started) == 2


def test_data_action_sent_while_the_app_is_stopping_still_runs_before_the_start() -> None:
    h = Harness()
    h.queued_while_stopping = [DATA_ACTION]

    h.requests.append({"action": "restart"})
    h.supervisor.tick(0.0)

    assert h.data_actions == [(DATA_ACTION, 1, 1)]
    assert len(h.started) == 2


def test_data_action_after_a_failed_start_runs_without_a_stop() -> None:
    h = Harness()
    h.started[0].exit_code = 1
    h.supervisor.tick(0.0)

    h.requests.append(DATA_ACTION)
    h.supervisor.tick(1.0)

    assert h.data_actions == [(DATA_ACTION, 1, 0)]
    assert len(h.started) == 2


def test_a_crashing_data_action_is_reported_and_the_app_starts_again() -> None:
    h = Harness()
    h.data_action_error = RuntimeError("disk on fire")

    h.requests.append(DATA_ACTION)
    assert h.supervisor.tick(0.0) is None

    assert any("Data action failed: disk on fire" in message for message in h.messages)
    assert len(h.started) == 2


def test_run_data_action_leaves_the_outcome_and_opens_the_reset_app_on_its_start_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from desktop import dev_data_actions

    state_file = tmp_path / "state.json"
    sup.save_window_state(state_file, FakeWindow())
    outcome = {"operation": "backup", "target": "db", "ok": True, "message": "Moved Database to backup (x)."}
    monkeypatch.setattr(dev_data_actions, "perform", lambda request: outcome)

    assert sup.read_data_action(tmp_path) is None
    assert sup.run_data_action(DATA_ACTION, tmp_path, state_file) == "Moved Database to backup (x)."

    assert sup.read_data_action(tmp_path) == {**outcome, "finished_at": sup.read_data_action(tmp_path)["finished_at"]}
    assert sup.load_window_state(state_file) == ("", {"x": 40, "y": 60, "width": 1400, "height": 900})


@pytest.mark.parametrize(
    "outcome",
    [
        {"operation": "restore", "target": "db", "ok": True, "message": "Restored."},
        {"operation": "backup", "target": "input", "ok": True, "message": "Moved downloads."},
        {"operation": "delete", "target": "db", "ok": False, "message": "Data action failed: locked."},
    ],
)
def test_run_data_action_keeps_the_route_when_the_database_is_still_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: dict[str, object]
) -> None:
    from desktop import dev_data_actions

    state_file = tmp_path / "state.json"
    sup.save_window_state(state_file, FakeWindow())
    monkeypatch.setattr(dev_data_actions, "perform", lambda request: outcome)

    sup.run_data_action(DATA_ACTION, tmp_path, state_file)

    assert sup.load_window_state(state_file)[0] == "/#/empresas/4170"
    assert sup.read_data_action(tmp_path)["ok"] is outcome["ok"]


def test_run_data_action_reports_a_broken_data_actions_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from desktop import dev_data_actions

    def broken(_request: dict[str, object]) -> dict[str, object]:
        raise ImportError("dev_data_actions has a syntax error")

    monkeypatch.setattr(dev_data_actions, "perform", broken)

    message = sup.run_data_action(DATA_ACTION, tmp_path, tmp_path / "state.json")

    assert message == "Data action failed: dev_data_actions has a syntax error"
    assert sup.read_data_action(tmp_path)["ok"] is False
