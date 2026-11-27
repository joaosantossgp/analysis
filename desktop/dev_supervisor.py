"""Dev supervisor: the long-lived parent of `python -m desktop.app --dev`.

Source-mode dev tooling only; the packaged app never runs this module. The
supervisor runs the app as a child process, restarts it when a Python source of
the desktop shell or core changes, and stays alive when the new code fails to
start. It imports the standard library only, so broken app code cannot take it
down.
"""

from __future__ import annotations

import functools
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

# Path of the JSON file that carries the last route and window geometry from
# one child to the next. Its presence also marks a process as a supervised child.
STATE_FILE_ENV = "CVMANALYTICS_DEV_STATE_FILE"
WATCHED_DIRS = ("desktop", "src")
POLL_SECONDS = 0.5
QUIET_SECONDS = 1.0
STOP_TIMEOUT_SECONDS = 10

Snapshot = dict[str, tuple[int, int]]

# Flushed so supervisor messages land after the child's traceback even when
# the output is redirected to a file.
_report = functools.partial(print, flush=True)


def should_supervise(argv: Sequence[str], environ: Mapping[str, str]) -> bool:
    """Only a `--dev` launch that is not already a supervised child."""
    return "--dev" in argv and STATE_FILE_ENV not in environ


def scan_sources(repo_root: Path) -> Snapshot:
    """Map each watched Python source to `(mtime_ns, size)`."""
    snapshot: Snapshot = {}
    for watched in WATCHED_DIRS:
        for directory, subdirectories, files in os.walk(repo_root / watched):
            subdirectories[:] = [d for d in subdirectories if d != "__pycache__" and not d.startswith(".")]
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = Path(directory) / name
                try:
                    stat = path.stat()
                except OSError:  # deleted between the walk and the stat
                    continue
                snapshot[path.relative_to(repo_root).as_posix()] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


class DevSupervisor:
    """Decides when the app child starts, restarts, and when dev mode ends.

    Process handling is injected so the decisions run in tests without a
    process or a window. `tick` is one poll step.
    """

    def __init__(
        self,
        start_child: Callable[[], Any],
        stop_child: Callable[[Any], None],
        scan: Callable[[], Snapshot],
        report: Callable[[str], None] = _report,
        quiet_seconds: float = QUIET_SECONDS,
    ) -> None:
        self._start_child = start_child
        self._stop_child = stop_child
        self._scan = scan
        self._report = report
        self._quiet_seconds = quiet_seconds
        self._child: Any = None
        self._snapshot: Snapshot = {}
        self._changed: set[str] = set()
        self._last_change_at = 0.0

    def start(self) -> None:
        self._snapshot = self._scan()
        self._child = self._start_child()

    def tick(self, now: float) -> int | None:
        """Run one poll step; return the exit code once dev mode should end."""
        snapshot = self._scan()
        changed = {
            name
            for name in snapshot.keys() | self._snapshot.keys()
            if snapshot.get(name) != self._snapshot.get(name)
        }
        if changed:
            self._snapshot = snapshot
            self._changed |= changed
            self._last_change_at = now

        if self._child is not None:
            exit_code = self._child.poll()
            if exit_code == 0:
                return 0  # the user closed the window
            if exit_code is not None:
                self._child = None
                self._report(
                    f"[dev] The app stopped with exit code {exit_code}; the error and traceback are above.\n"
                    "[dev] Dev mode is still running: save a Python file under desktop/ or src/ to "
                    "start the app again, or press Ctrl+C to quit."
                )

        if self._changed and now - self._last_change_at >= self._quiet_seconds:
            names = sorted(self._changed)
            self._changed = set()
            more = f" (+{len(names) - 3} more)" if len(names) > 3 else ""
            self._report(f"[dev] Python change in {', '.join(names[:3])}{more}; restarting the app.")
            if self._child is not None:
                self._stop_child(self._child)
            self._child = self._start_child()
        return None

    def shutdown(self) -> None:
        if self._child is not None and self._child.poll() is None:
            self._stop_child(self._child)
        self._child = None


def stop_child(proc: Any) -> None:
    """Ask the child to close its window and exit; kill its tree if it does not.

    Closing stdin is the stop request (see `watch_for_stop`). A clean exit lets
    the child save its window state, release the runtime lock and stop Vite.
    """
    try:
        proc.stdin.close()
        proc.wait(timeout=STOP_TIMEOUT_SECONDS)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        if os.name == "nt":
            # /T also ends the Vite dev server the child started.
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            proc.kill()
        proc.wait(timeout=STOP_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        pass


def run(argv: Sequence[str], *, repo_root: Path | None = None) -> int:
    """Supervise `python -m desktop.app <argv>` until the window is closed."""
    root = repo_root or Path(__file__).resolve().parent.parent
    state_file = Path(tempfile.gettempdir()) / f"cvmanalytics-dev-state-{os.getpid()}.json"
    environment = {**os.environ, STATE_FILE_ENV: str(state_file)}

    def start_child() -> Any:
        return subprocess.Popen(
            [sys.executable, "-m", "desktop.app", *argv],
            cwd=str(root),
            env=environment,
            stdin=subprocess.PIPE,
        )

    supervisor = DevSupervisor(start_child, stop_child, lambda: scan_sources(root))
    _report("[dev] Dev supervisor running: the app restarts when Python files under desktop/ or src/ change.")
    try:
        supervisor.start()
        while True:
            exit_code = supervisor.tick(time.monotonic())
            if exit_code is not None:
                return exit_code
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        return 130
    finally:
        supervisor.shutdown()
        state_file.unlink(missing_ok=True)


# --- Child side: continuity across restarts -----------------------------------

_GEOMETRY_KEYS = ("x", "y", "width", "height")
_MINIMIZED_COORDINATE = -30000  # Windows parks a minimized window at -32000


def load_window_state(path: Path) -> tuple[str, dict[str, int]]:
    """Return `(route, geometry)` saved by the previous child, or `("", {})`.

    The route is origin-relative because the Vite dev port can change between
    runs. Geometry is all of x/y/width/height or nothing.
    """
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        route, saved = state.get("route"), state.get("geometry")
    except (OSError, ValueError, AttributeError):
        return "", {}
    if not (isinstance(route, str) and route.startswith("/")):
        route = ""
    try:
        geometry = {key: saved[key] for key in _GEOMETRY_KEYS}
    except (KeyError, TypeError):
        return route, {}
    return route, geometry if all(type(value) is int for value in geometry.values()) else {}


def save_window_state(path: Path, window: Any) -> None:
    """Record the window's route and geometry; a failed read keeps the old value."""
    route, geometry = load_window_state(path)
    try:
        current = window.evaluate_js("location.href.slice(location.origin.length)")
        if isinstance(current, str) and current.startswith("/"):
            route = current
    except Exception:  # page not loaded, window already gone
        pass
    try:
        current_geometry = {key: int(getattr(window, key)) for key in _GEOMETRY_KEYS}
        if current_geometry["x"] > _MINIMIZED_COORDINATE:
            geometry = current_geometry
    except Exception:
        pass
    try:
        path.write_text(json.dumps({"route": route, "geometry": geometry}), encoding="utf-8")
    except OSError:
        pass


def watch_for_stop(
    path: Path,
    window: Any,
    close_windows: Callable[[], None],
    read: Callable[[], bytes] = lambda: os.read(0, 1),
) -> threading.Thread:
    """Close the app when the supervisor closes this process's stdin.

    Runs on a daemon thread so the blocked read never keeps the app alive. The
    read is unbuffered (`os.read`) because a daemon thread parked inside
    `sys.stdin` can abort interpreter shutdown.
    """

    def wait_then_close() -> None:
        try:
            read()
        except OSError:
            pass
        save_window_state(path, window)
        close_windows()

    thread = threading.Thread(target=wait_then_close, name="desktop-dev-stop-listener", daemon=True)
    thread.start()
    return thread
