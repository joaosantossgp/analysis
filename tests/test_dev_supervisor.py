from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

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
        self.supervisor = sup.DevSupervisor(
            start_child=self._start,
            stop_child=self.stopped.append,
            scan=lambda: dict(self.snapshot),
            report=self.messages.append,
            quiet_seconds=1.0,
        )
        self.supervisor.start()

    def _start(self) -> FakeChild:
        child = FakeChild()
        self.started.append(child)
        return child

    def save(self, name: str = "desktop/app.py") -> None:
        mtime, size = self.snapshot.get(name, (0, 0))
        self.snapshot[name] = (mtime + 1, size)


def test_supervises_only_source_dev_launches_that_are_not_already_children() -> None:
    assert sup.should_supervise(["--dev"], frozen=False, environ={}) is True
    assert sup.should_supervise(["--dev", "--debug"], frozen=False, environ={}) is True
    assert sup.should_supervise([], frozen=False, environ={}) is False
    assert sup.should_supervise(["--vite"], frozen=False, environ={}) is False
    assert sup.should_supervise(["--dev"], frozen=True, environ={}) is False
    assert sup.should_supervise(["--dev"], frozen=False, environ={sup.STATE_FILE_ENV: "x.json"}) is False


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
        sup.stop_child(proc)

    proc.stdin.close.assert_called_once_with()
    proc.wait.assert_called_once_with(timeout=sup.STOP_TIMEOUT_SECONDS)
    run.assert_not_called()
    proc.kill.assert_not_called()


def test_stop_child_kills_the_process_tree_when_the_child_does_not_exit() -> None:
    proc = Mock(pid=4242)
    proc.wait.side_effect = [subprocess.TimeoutExpired("app", sup.STOP_TIMEOUT_SECONDS), 1]

    with patch.object(sup.subprocess, "run") as run, patch.object(sup.os, "name", "nt"):
        sup.stop_child(proc)

    run.assert_called_once_with(
        ["taskkill", "/PID", "4242", "/T", "/F"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


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
