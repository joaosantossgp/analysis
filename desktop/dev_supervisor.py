"""Dev supervisor: the long-lived parent of `python -m desktop.app --dev`.

Source-mode dev tooling only; the packaged app never runs this module. The
supervisor runs the app as a child process, restarts it when a Python source of
the desktop shell or core changes, and stays alive when the new code fails to
start. It imports the standard library only, so broken app code cannot take it
down.

The app talks back through a control directory (`CONTROL_DIR_ENV`): it queues
requests as JSON files under `requests/` (`send_request`) and reads the
supervisor's `status.json` (`read_status`). The dev panel's restart button and
auto-restart switch use this channel.
"""

from __future__ import annotations

import functools
import itertools
import json
import os
import shutil
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
# Directory the supervisor shares with its child: requests in, status out.
CONTROL_DIR_ENV = "CVMANALYTICS_DEV_CONTROL_DIR"
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
    process or a window. `tick` is one poll step. `read_requests` returns the
    requests the app queued since the last call; `publish_status` receives the
    status whenever it changes.
    """

    def __init__(
        self,
        start_child: Callable[[], Any],
        stop_child: Callable[[Any], None],
        scan: Callable[[], Snapshot],
        report: Callable[[str], None] = _report,
        quiet_seconds: float = QUIET_SECONDS,
        read_requests: Callable[[], list[dict[str, Any]]] = list,
        publish_status: Callable[[dict[str, Any]], None] = lambda status: None,
    ) -> None:
        self._start_child = start_child
        self._stop_child = stop_child
        self._scan = scan
        self._report = report
        self._quiet_seconds = quiet_seconds
        self._read_requests = read_requests
        self._publish_status = publish_status
        self._published: dict[str, Any] | None = None
        self._auto_restart = True
        self._child: Any = None
        self._snapshot: Snapshot = {}
        self._changed: set[str] = set()
        self._last_change_at = 0.0

    def start(self) -> None:
        self._snapshot = self._scan()
        self._publish()
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

        restart_reason = self._apply(self._read_requests())

        # Auto-restart off holds a running window still. With no window there
        # is no dev panel to restart from, so a change always starts the app.
        change_restarts = self._auto_restart or self._child is None
        if (
            restart_reason is None
            and change_restarts
            and self._changed
            and now - self._last_change_at >= self._quiet_seconds
        ):
            names = sorted(self._changed)
            more = f" (+{len(names) - 3} more)" if len(names) > 3 else ""
            restart_reason = f"Python change in {', '.join(names[:3])}{more}"
        if restart_reason is not None:
            self._changed = set()
            self._report(f"[dev] {restart_reason}; restarting the app.")
            if self._child is not None:
                self._stop_child(self._child)
            # The restart just done answers restart requests queued meanwhile; apply the rest.
            self._apply([request for request in self._read_requests() if request.get("action") != "restart"])
            self._child = self._start_child()
        self._publish()
        return None

    def _apply(self, requests: list[dict[str, Any]]) -> str | None:
        """Apply the app's requests; return the restart reason when one asks for a restart."""
        restart_reason = None
        for request in requests:
            action = request.get("action")
            if action == "restart":
                restart_reason = "Restart requested from the app"
            elif action == "set_auto_restart" and isinstance(request.get("enabled"), bool):
                self._auto_restart = request["enabled"]
                self._report(f"[dev] Automatic restart turned {'on' if self._auto_restart else 'off'}.")
            else:
                self._report(f"[dev] Ignored an unknown request from the app: {request!r}")
        return restart_reason

    def _publish(self) -> None:
        status = {"auto_restart": self._auto_restart, "pending_changes": len(self._changed)}
        if status == self._published:
            return
        try:
            self._publish_status(status)
        except OSError:
            return  # retried on the next tick
        self._published = status

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
    control_dir = Path(tempfile.mkdtemp(prefix="cvmanalytics-dev-"))
    environment = {**os.environ, STATE_FILE_ENV: str(state_file), CONTROL_DIR_ENV: str(control_dir)}

    def start_child() -> Any:
        return subprocess.Popen(
            [sys.executable, "-m", "desktop.app", *argv],
            cwd=str(root),
            env=environment,
            stdin=subprocess.PIPE,
        )

    supervisor = DevSupervisor(
        start_child,
        stop_child,
        lambda: scan_sources(root),
        read_requests=lambda: read_requests(control_dir),
        publish_status=lambda status: write_status(control_dir, status),
    )
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
        shutil.rmtree(control_dir, ignore_errors=True)


# --- Control directory: requests from the app, status from the supervisor -----


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write through a rename so the other process never reads half a file."""
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(temporary, path)


_request_numbers = itertools.count()


def send_request(control_dir: Path, action: str, **params: Any) -> None:
    """App side: queue `{"action": action, **params}` for the supervisor. Raises OSError."""
    requests = control_dir / "requests"
    requests.mkdir(parents=True, exist_ok=True)
    # The clock is coarse on Windows: the counter keeps names unique and in order.
    name = f"{time.time_ns():020d}-{os.getpid()}-{next(_request_numbers):06d}.json"
    _write_json(requests / name, {"action": action, **params})


def read_requests(control_dir: Path) -> list[dict[str, Any]]:
    """Supervisor side: take the queued requests, oldest first. Unreadable ones are dropped."""
    taken: list[dict[str, Any]] = []
    for path in sorted((control_dir / "requests").glob("*.json")):
        try:
            request = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            request = None
        try:
            path.unlink()
        except OSError:
            continue  # locked by the writer; taken on the next poll
        if isinstance(request, dict):
            taken.append(request)
    return taken


def write_status(control_dir: Path, status: dict[str, Any]) -> None:
    """Supervisor side: publish the status the app shows. Raises OSError."""
    _write_json(control_dir / "status.json", status)


def read_status(control_dir: Path) -> dict[str, Any]:
    """App side: the supervisor's last published status, or `{}`."""
    try:
        status = json.loads((control_dir / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return status if isinstance(status, dict) else {}


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
