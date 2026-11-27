"""Dev supervisor: the long-lived parent of `python -m desktop.app --dev`.

Source-mode dev tooling only; the packaged app never runs this module. The
supervisor runs the app as a child process, restarts it when a Python source of
the desktop shell or core changes, and stays alive when the new code fails to
start. It imports the standard library, plus the stdlib-only `dev_data` and
`dev_bootstrap` modules once at launch, so later edits to app code cannot take
it down.

The app talks back through a control directory (`CONTROL_DIR_ENV`): it queues
requests as JSON files under `requests/` (`send_request`) and reads the
supervisor's `status.json` (`read_status`). The dev panel's restart button and
auto-restart switch use this channel, and so do its dev data actions: the
supervisor runs them between stopping and starting the app and leaves the
outcome in `data_action.json` (`read_data_action`).

Worktree switch: the child runs the code of the active worktree. Every worktree
runs on the environment of the checkout dev mode was launched from (its `.venv`
and `node_modules`), so a worktree is switchable when its dependency manifests
match that environment (`dev_data.list_worktrees`). A data action acts on the
dev data the requesting app resolved, so after a switch it is the active
worktree's, and the app restarts on the active worktree.
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
# The checkout dev mode was launched from; its installed environment runs every worktree.
LAUNCH_ROOT_ENV = "CVMANALYTICS_DEV_LAUNCH_ROOT"
WATCHED_DIRS = ("desktop", "src")
POLL_SECONDS = 0.5
QUIET_SECONDS = 1.0
STOP_TIMEOUT_SECONDS = 10
MAX_REQUEST_BYTES = 64 * 1024  # a request is a few dozen bytes
DATA_ACTION_FILE = "data_action.json"  # outcome of the last dev data action
# shortcut: a switched-to app that exits with an error this soon after it started
# counts as a failed switch (the child sends no "window is up" signal); add one
# if a slow first start ever outlasts it.
SWITCH_GRACE_SECONDS = 60.0

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
    status whenever it changes. `stop_child` returns whether the child exited.
    `run_data_action` performs a dev data action and returns the message to report.

    With a `launch_root`, `active_root` is the worktree whose code
    `start_child` runs and `scan` watches. `list_worktrees` returns the
    `dev_data.list_worktrees` entries a switch request is checked against.
    """

    def __init__(
        self,
        start_child: Callable[[], Any],
        stop_child: Callable[[Any], bool],
        scan: Callable[[], Snapshot],
        report: Callable[[str], None] = _report,
        quiet_seconds: float = QUIET_SECONDS,
        read_requests: Callable[[], list[dict[str, Any]]] = list,
        publish_status: Callable[[dict[str, Any]], None] = lambda status: None,
        run_data_action: Callable[[dict[str, Any]], str] = lambda request: "Data actions are not available.",
        list_worktrees: Callable[[], list[dict[str, Any]]] = list,
        launch_root: Path | None = None,
    ) -> None:
        self._start_child = start_child
        self._stop_child = stop_child
        self._scan = scan
        self._report = report
        self._quiet_seconds = quiet_seconds
        self._read_requests = read_requests
        self._publish_status = publish_status
        self._run_data_action = run_data_action
        self._data_actions: list[dict[str, Any]] = []
        self._published: dict[str, Any] | None = None
        self._auto_restart = True
        self._child: Any = None
        self._stop_failed = False
        self._snapshot: Snapshot = {}
        self._changed: set[str] = set()
        self._last_change_at = 0.0
        self._list_worktrees = list_worktrees
        self._launch_root = launch_root
        self.active_root = launch_root
        self._previous_root: Path | None = None  # set until a switch is confirmed
        self._worktree_notice: str | None = None
        self._now = 0.0
        self._started_at = 0.0

    def start(self) -> None:
        self._snapshot = self._scan()
        self._publish()
        self._start()

    def tick(self, now: float) -> int | None:
        """Run one poll step; return the exit code once dev mode should end."""
        self._now = now
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

        restart_reason = None
        if self._child is not None:
            exit_code = self._child.poll()
            if exit_code is not None and self._stop_failed:
                self._child = None  # the app that did not stop has exited after all
            elif exit_code == 0:
                return 0  # the user closed the window
            elif exit_code is not None and self._switch_pending():
                self._child = None
                restart_reason = self._return_from_failed_switch(
                    f"the app exited with code {exit_code} (traceback in the terminal)"
                )
            elif exit_code is not None:
                self._child = None
                self._previous_root = None
                self._report(
                    f"[dev] The app stopped with exit code {exit_code}; the error and traceback are above.\n"
                    "[dev] Dev mode is still running: save a Python file under desktop/ or src/ to "
                    "start the app again, or press Ctrl+C to quit."
                )
            elif self._previous_root is not None and not self._switch_pending():
                self._previous_root = None  # the switched-to app is up: the switch is done

        if self._active_worktree_removed():
            removed = self.active_root
            self._previous_root = None
            self._enter(self._launch_root)
            self._worktree_notice = f"Worktree {removed.name} was removed; the window is back on {self.active_root.name}."
            restart_reason = f"Worktree {removed.name} was removed"

        restart_reason = self._apply(self._read_requests()) or restart_reason
        if restart_reason is None and self._stop_failed:
            restart_reason = "The last restart did not finish"

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
            self._restart(restart_reason)
        self._publish()
        return None

    def _restart(self, reason: str) -> None:
        self._report(f"[dev] {reason}; restarting the app.")
        if self._child is not None:
            # A second app would fight the old one for the runtime lock and the port.
            if not self._stop_child(self._child):
                self._stop_failed = True
                self._report(
                    "[dev] The app did not stop, so no new app was started. Dev mode tries again on "
                    "the next poll; if this repeats, close the window or end the process."
                )
                return
            self._child = None
        self._stop_failed = False
        self._changed = set()
        # The restart just done answers restart requests queued meanwhile; apply the rest.
        self._apply([request for request in self._read_requests() if request.get("action") != "restart"])
        self._run_data_actions()
        self._start()

    def _start(self) -> None:
        try:
            self._child = self._start_child()
            self._started_at = self._now
        except OSError as error:  # the child stays None, so the next change or restart request starts it
            if self._previous_root is not None:
                self._return_from_failed_switch(f"could not start the app: {error}")
                self._report(f"[dev] {self._worktree_notice}")
                self._start()  # on the previous worktree; no further fallback
                return
            self._report(
                f"[dev] Could not start the app: {error}\n"
                "[dev] Dev mode is still running: save a Python file under desktop/ or src/ to "
                "try again, or press Ctrl+C to quit."
            )

    def _apply(self, requests: list[dict[str, Any]]) -> str | None:
        """Apply the app's requests; return the restart reason when one asks for a restart."""
        restart_reason = None
        for request in requests:
            action = request.get("action")
            if action == "restart":
                restart_reason = "Restart requested from the app"
            elif action == "data_action":
                self._data_actions.append(request)  # run once the app is stopped (`_restart`)
                restart_reason = "Data action requested from the app"
            elif action == "set_auto_restart" and isinstance(request.get("enabled"), bool):
                self._auto_restart = request["enabled"]
                self._report(f"[dev] Automatic restart turned {'on' if self._auto_restart else 'off'}.")
            elif action == "switch_worktree" and isinstance(request.get("path"), str) and self._launch_root:
                restart_reason = self._switch(request["path"]) or restart_reason
            else:
                self._report(f"[dev] Ignored an unknown request from the app: {request!r}")
        return restart_reason

    def _run_data_actions(self) -> None:
        """Run the queued dev data actions; the app is stopped, so no database handle is open."""
        queued, self._data_actions = self._data_actions, []
        for request in queued:
            try:
                self._report(f"[dev] {self._run_data_action(request)}")
            except Exception as error:  # the app is started again whatever happens
                self._report(f"[dev] Data action failed: {error}")

    # --- Worktree switch ---------------------------------------------------------

    def _switch(self, path: str) -> str | None:
        """Point the child at another worktree; return the restart reason, or None when refused."""
        entry = None
        try:
            entry = next((w for w in self._list_worktrees() if Path(w["path"]) == Path(path)), None)
            refusal = switch_refusal(entry, path)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            refusal = f"Could not list the worktrees: {error}"
        if refusal is not None:
            self._worktree_notice = refusal
            self._report(f"[dev] Worktree switch refused: {refusal}")
            return None
        target = Path(entry["path"])
        if target != self.active_root:
            self._previous_root = self.active_root
        self._started_at = self._now  # the old app's age must not confirm the switch
        self._enter(target)
        self._worktree_notice = None
        self._publish()  # lets the app confirm the switch before it is stopped
        return f"Switching to worktree {target.name}"

    def _enter(self, root: Path) -> None:
        """Make `root` the active worktree; its sources become the watched ones."""
        self.active_root = root
        self._snapshot, self._changed = self._scan(), set()

    def _switch_pending(self) -> bool:
        return self._previous_root is not None and self._now - self._started_at < SWITCH_GRACE_SECONDS

    def _return_from_failed_switch(self, reason: str) -> str:
        failed, previous = self.active_root, self._previous_root
        self._previous_root = None
        self._enter(previous)
        self._worktree_notice = f"Switching to {failed.name} failed: {reason}. The window is back on {previous.name}."
        return f"Switching to {failed.name} failed; returning to {previous.name}"

    def _active_worktree_removed(self) -> bool:
        if self.active_root is None or self.active_root == self._launch_root:
            return False
        return not (self.active_root / ".git").exists()  # `git worktree remove` deletes it first

    def _publish(self) -> None:
        status = {"auto_restart": self._auto_restart, "pending_changes": len(self._changed)}
        if self.active_root is not None:
            status.update(worktree=str(self.active_root), worktree_notice=self._worktree_notice)
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


def switch_refusal(entry: dict[str, Any] | None, path: str) -> str | None:
    """Why the window cannot switch to `path`, whose `dev_data.list_worktrees` row is `entry`; None when it can."""
    if entry is None:
        return f"{path} is not a worktree of this repository (it may have been removed)."
    if entry["dependency_differences"]:
        differing = " and ".join(entry["dependency_differences"])
        return f"{entry['name']} needs its own dependencies ({differing} differ); supported in a later version."
    return None


def stop_child(proc: Any) -> bool:
    """Ask the child to close its window and exit; kill its tree if it does not.

    Closing stdin is the stop request (see `watch_for_stop`). A clean exit lets
    the child save its window state, release the runtime lock and stop Vite.
    Returns whether the child exited. Never raises; each step is time-limited.
    """
    try:
        proc.stdin.close()
        proc.wait(timeout=STOP_TIMEOUT_SECONDS)
        return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        if os.name == "nt":
            # /T also ends the Vite dev server the child started.
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                check=False,
                timeout=STOP_TIMEOUT_SECONDS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            proc.kill()
    except (OSError, subprocess.SubprocessError):
        pass  # the wait below tells whether the child is gone
    try:
        proc.wait(timeout=STOP_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def run(argv: Sequence[str], *, repo_root: Path | None = None) -> int:
    """Supervise `python -m desktop.app <argv>` until the window is closed."""
    root = repo_root or Path(__file__).resolve().parent.parent
    state_file = Path(tempfile.gettempdir()) / f"cvmanalytics-dev-state-{os.getpid()}.json"
    control_dir = Path(tempfile.mkdtemp(prefix="cvmanalytics-dev-"))
    environment = {
        **os.environ,
        STATE_FILE_ENV: str(state_file),
        CONTROL_DIR_ENV: str(control_dir),
        LAUNCH_ROOT_ENV: str(root),
    }
    # Imported now, not on the first switch, so a later edit cannot break the supervisor.
    from desktop import dev_bootstrap, dev_data  # noqa: PLC0415 - stdlib-only dev modules

    def start_child() -> Any:
        checkout = supervisor.active_root
        command = [sys.executable, "-m", "desktop.app", *argv]
        if checkout != root:
            # Another worktree runs on this checkout's environment: no install. Calling
            # main() skips that worktree's own bootstrap (any version of it), which
            # would provision a .venv and node_modules of its own.
            dev_bootstrap.link_frontend_dependencies(root, checkout)
            command = [sys.executable, "-c", "from desktop.app import main; main()", *argv]
        return subprocess.Popen(command, cwd=str(checkout), env=environment, stdin=subprocess.PIPE)

    supervisor = DevSupervisor(
        start_child,
        stop_child,
        lambda: scan_sources(supervisor.active_root),
        read_requests=lambda: read_requests(control_dir),
        publish_status=lambda status: write_status(control_dir, status),
        run_data_action=lambda request: run_data_action(request, control_dir, state_file),
        list_worktrees=lambda: dev_data.list_worktrees(root, env_root=root),
        launch_root=root,
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


def read_requests(control_dir: Path, report: Callable[[str], None] = _report) -> list[dict[str, Any]]:
    """Supervisor side: take the queued requests, oldest first. Unreadable ones are reported and dropped."""
    taken: list[dict[str, Any]] = []
    for path in sorted((control_dir / "requests").glob("*.json")):
        request: Any
        try:
            with path.open("rb") as file:
                data = file.read(MAX_REQUEST_BYTES + 1)
            if len(data) > MAX_REQUEST_BYTES:
                raise ValueError(f"larger than {MAX_REQUEST_BYTES // 1024} KB")
            request = json.loads(data)
        except (OSError, ValueError, RecursionError) as error:  # RecursionError: deeply nested JSON
            request = error
        try:
            path.unlink()
        except OSError:
            continue  # locked by the writer; taken on the next poll
        if isinstance(request, dict):
            taken.append(request)
        else:
            reason = request if isinstance(request, Exception) else "not a JSON object"
            report(f"[dev] Ignored an unreadable request from the app ({path.name}): {reason}")
    return taken


def run_data_action(request: dict[str, Any], control_dir: Path, state_file: Path) -> str:
    """Supervisor side: perform a dev data action with the app stopped; leave the outcome for the next app."""
    try:
        # Imported here: a broken module fails the data action, not dev mode.
        from desktop import dev_data_actions  # noqa: PLC0415

        result = dev_data_actions.perform(request)
    except Exception as error:
        result = {"operation": request.get("operation"), "target": request.get("target"), "ok": False,
                  "message": f"Data action failed: {error}"}
    if result["ok"] and result["operation"] != "restore" and result["target"] != "input":
        # The database is gone: open on the start page, where the app shows its empty first-run state.
        _route, geometry = load_window_state(state_file)
        try:
            state_file.write_text(json.dumps({"route": "", "geometry": geometry}), encoding="utf-8")
        except OSError:
            pass
    try:
        _write_json(control_dir / DATA_ACTION_FILE, {**result, "finished_at": time.strftime("%Y-%m-%d %H:%M:%S")})
    except OSError:
        pass  # the terminal still has the message
    return result["message"]


def read_data_action(control_dir: Path) -> dict[str, Any] | None:
    """App side: the outcome of the last dev data action of this dev session, or None."""
    try:
        outcome = json.loads((control_dir / DATA_ACTION_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return outcome if isinstance(outcome, dict) else None


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
