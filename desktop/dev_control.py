"""Agent command for the open dev mode window: report what it runs, switch its worktree.

    python -m desktop.dev_control status
    python -m desktop.dev_control switch [<worktree path, folder name or branch>]

Source-mode dev tooling, standard library only; run it from the root of any
checkout of this repository. It finds the running dev supervisor through the
record the supervisor leaves under the git common dir
(`dev_supervisor.register`) and talks to it over the dev panel's control
directory: the same switch request, refusals, dependency install and
failed-switch fallback as the panel. `switch` without a target switches to the
checkout the command runs from, and returns once the outcome is known. Exit
code 0 on success, 1 on any failure (the reason goes to stderr).

Agents run `switch` only when the owner asks, never on their own (`AGENTS.md`).
Vocabulary: `GLOSSARY.md`, "Development".
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from desktop import dev_data, dev_supervisor, lockfile

POLL_SECONDS = 0.5
# As in the dev panel: longer than the supervisor can be busy stopping the app.
CONFIRM_TIMEOUT_SECONDS = 15.0

# Flushed: an agent reading a pipe sees each progress line as it happens.
_say = functools.partial(print, flush=True)


class ControlError(Exception):
    """The command failed; the message says why."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _same_path(value: Any, path: Path) -> bool:
    """Whether `value`, a path string read from a status or listing, names `path`."""
    return isinstance(value, str) and os.path.normcase(Path(value).resolve()) == os.path.normcase(path.resolve())


def _dict_or_none(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


# --- Finding the running supervisor ---------------------------------------------


def find_supervisors(repo_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """The running dev supervisors of this repository, and why each stale record was removed.

    A record is stale when its supervisor ended without removing it (killed)
    or its control directory is gone.
    """
    try:
        paths = sorted(dev_supervisor.registry_dir(repo_root).glob("*.json"))
    except (OSError, ValueError):
        return [], []  # not a git checkout, so nothing can be registered for it
    live: list[dict[str, Any]] = []
    stale: list[str] = []
    for path in paths:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            pid, control_dir, launch_root = int(record["pid"]), Path(record["control_dir"]), record["launch_root"]
        except (OSError, ValueError, KeyError, TypeError) as error:
            stale.append(f"unreadable record {path.name} ({error})")
        else:
            # shortcut: a PID reused by another process passes for a live supervisor, so the
            # switch then times out unconfirmed; add a heartbeat to the status if that bites.
            if not lockfile._pid_alive(pid):
                stale.append(f"the dev supervisor launched from {launch_root} (PID {pid}) is no longer running")
            elif not control_dir.is_dir():
                stale.append(f"the control directory of the dev supervisor launched from {launch_root} (PID {pid}) is gone")
            else:
                live.append(record)
                continue
        with contextlib.suppress(OSError):
            path.unlink()
    return live, stale


def _supervisors(repo_root: Path, pid: int | None) -> list[dict[str, Any]]:
    live, stale = find_supervisors(repo_root)
    if pid is not None:
        live = [record for record in live if record["pid"] == pid]
    if not live:
        which = f"with supervisor PID {pid} " if pid is not None else ""
        removed = "".join(f"\nRemoved a stale record: {reason}." for reason in stale)
        raise ControlError(
            f"No dev mode {which}is running for this repository; the owner starts it with "
            f"`python -m desktop.app --dev`.{removed}"
        )
    return live


# --- status ---------------------------------------------------------------------


def _list_worktrees(launch_root: Path) -> list[dict[str, Any]]:
    """The worktree rows the supervisor checks a switch against."""
    return dev_data.list_worktrees(launch_root, env_root=launch_root)


def _notice(state: dict[str, Any]) -> str | None:
    """The supervisor's last word on a switch, with the command and output of a failed install."""
    notice = state.get("worktree_notice")
    if not isinstance(notice, str):
        return None
    detail = _dict_or_none(state.get("worktree_notice_detail"))
    if detail:
        if detail.get("command"):
            notice += f"\nCommand: {detail['command']} (exit code {detail.get('exit_code')})"
        notice += f"\n{detail.get('output')}"
    return notice


def _data_mode(record: dict[str, Any], worktree: Path, main: Path | None) -> str:
    """The window's data mode and path, decided as `dev_get_context` does in the app."""
    if record.get("use_release_data"):
        return "installed-app"
    resolved = dev_data.resolve(worktree, main=main)
    explicit = record.get("cvm_data_dir")
    if explicit and not _same_path(explicit, resolved.data_root):
        return f"custom ({explicit})"
    return f"{resolved.mode} ({resolved.data_root})"


def print_status(record: dict[str, Any], repo_root: Path) -> None:
    state = dev_supervisor.read_status(Path(record["control_dir"]))
    launch_root = Path(record["launch_root"])
    _say(f"Dev mode: running (supervisor PID {record['pid']}, launched from {launch_root})")
    active = state.get("worktree")
    if not isinstance(active, str):
        _say("Active worktree: unknown (the dev supervisor has not published its status yet)")
        return
    try:
        rows, listing_error = _list_worktrees(launch_root), None
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        rows, listing_error = [], error
    row = next((row for row in rows if _same_path(row["path"], Path(active))), None)
    if row:
        branch = row["branch"] or "detached HEAD"
    else:
        branch = f"unknown ({listing_error or 'not in the worktree list'})"
    here = "the active worktree" if _same_path(active, repo_root) else "not the active worktree"
    install = _dict_or_none(state.get("install"))
    switching_from = state.get("switching_from")

    _say(f"Active worktree: {Path(active).name} ({active})")
    _say(f"This checkout: {repo_root.name}, {here}")
    _say(f"Branch: {branch}")
    _say(f"Data mode: {_data_mode(record, Path(active), Path(rows[0]['path']) if rows else None)}")
    if isinstance(switching_from, str):
        _say(
            f"Switch in progress: yes, from {Path(switching_from).name}; confirmed once the app has run "
            f"{dev_supervisor.SWITCH_GRACE_SECONDS:.0f} seconds"
        )
    else:
        _say("Switch in progress: no")
    if install:
        _say(f"Install in progress: dependencies for {install.get('name')}: {install.get('step')}")
    else:
        _say("Install in progress: no")
    notice = _notice(state)
    if notice:
        _say(f"Last switch notice: {notice}")


# --- switch ---------------------------------------------------------------------


def _find_worktree(rows: list[dict[str, Any]], target: str | None, repo_root: Path) -> dict[str, Any]:
    """The row `target` names by path, folder name or branch; with no target, this checkout's row."""
    if target is None:
        matches = [row for row in rows if _same_path(row["path"], repo_root)]
    else:
        matches = [row for row in rows if _same_path(row["path"], Path(target))]
        matches = matches or [row for row in rows if target in (row["name"], row["branch"])]
    if len(matches) == 1:
        return matches[0]
    listing = "".join(f"\n  {row['name']} ({row['branch'] or 'detached HEAD'}): {row['path']}" for row in rows)
    if matches:
        raise ControlError(f"{target} names several worktrees; pass the path of one:{listing}")
    raise ControlError(f"{target or repo_root} is not a worktree of this repository. Worktrees:{listing}")


def switch(record: dict[str, Any], repo_root: Path, target: str | None) -> None:
    """Switch the window to `target`, then wait for the outcome, as the dev panel does."""
    control_dir, launch_root = Path(record["control_dir"]), Path(record["launch_root"])
    try:
        rows = _list_worktrees(launch_root)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise ControlError(f"Could not list the worktrees: {error}") from error
    entry = _find_worktree(rows, target, repo_root)
    name, path = entry["name"], Path(entry["path"])

    state = dev_supervisor.read_status(control_dir)
    notice_before = state.get("worktree_notice")
    if _same_path(state.get("worktree"), path):
        if not state.get("switching_from"):
            _say(f"The window already runs {name}.")
            return
    else:
        # The supervisor checks the same again.
        refusal = dev_supervisor.switch_refusal(entry, entry["path"], _dict_or_none(state.get("install")))
        if refusal:
            raise ControlError(refusal)
        try:
            dev_supervisor.send_request(control_dir, "switch_worktree", path=entry["path"])
        except OSError as error:
            raise ControlError(f"Could not reach the dev supervisor: {error}") from error
        _say(f"Asked dev mode to switch the window to {name}.")
    _wait_for_switch(record, name, path, notice_before)


def _wait_for_switch(record: dict[str, Any], name: str, path: Path, notice_before: Any) -> None:
    """Follow the supervisor's status until the window runs `path` for good, or the switch failed."""
    control_dir, pid = Path(record["control_dir"]), int(record["pid"])
    deadline = time.monotonic() + CONFIRM_TIMEOUT_SECONDS
    accepted = False
    shown = None
    while True:
        if not (control_dir.is_dir() and lockfile._pid_alive(pid)):
            raise ControlError(f"Dev mode ended before the window switched to {name}.")
        state = dev_supervisor.read_status(control_dir)
        install = _dict_or_none(state.get("install"))
        line = None
        if _same_path(state.get("worktree"), path):
            previous = state.get("switching_from")
            if not previous:
                _say(f"The window runs {name}.")
                return
            accepted = True
            line = (
                f"The window is reopening on {name}. Waiting until the app has run "
                f"{dev_supervisor.SWITCH_GRACE_SECONDS:.0f} seconds; if it fails before that, dev mode "
                f"returns to {Path(previous).name}."
            )
        elif install and _same_path(install.get("worktree"), path):
            accepted = True
            line = f"Installing dependencies for {name}: {install.get('step')}..."
        elif accepted or state.get("worktree_notice") != notice_before:
            # Refused, install failed, the app failed on the worktree, or the worktree was removed.
            raise ControlError(_notice(state) or f"The window did not switch to {name}.")
        elif time.monotonic() >= deadline:
            raise ControlError("The dev supervisor did not confirm the switch.")
        if line and line != shown:
            _say(line)
            shown = line
        time.sleep(POLL_SECONDS)


# --- Entry point ----------------------------------------------------------------


def main(argv: list[str] | None = None, repo_root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m desktop.dev_control",
        description="Report or switch the worktree the open dev mode window runs. "
        "Agents run `switch` only when the owner asks.",
    )
    parser.add_argument("--pid", type=int, help="the dev supervisor to use when several dev mode windows run")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="print the active worktree, branch, data mode and any switch or install")
    switch_parser = commands.add_parser("switch", help="switch the open window to a worktree (only when the owner asks)")
    switch_parser.add_argument(
        "target", nargs="?", help="worktree path, folder name or branch (default: the checkout this runs from)"
    )
    args = parser.parse_args(argv)
    root = repo_root or _repo_root()
    try:
        supervisors = _supervisors(root, args.pid)
        if args.command == "status":
            for number, record in enumerate(supervisors):
                if number:
                    _say()
                print_status(record, root)
        elif len(supervisors) > 1:
            choices = "".join(f"\n  --pid {r['pid']}: launched from {r['launch_root']}" for r in supervisors)
            raise ControlError(f"Several dev mode windows are running; choose one:{choices}")
        else:
            switch(supervisors[0], root, args.target)
    except ControlError as error:
        print(f"error: {error}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
