"""Dev-only bridge methods behind the dev panel.

Source dev mode only: every method refuses in the packaged app, and the dev
modules are imported after that check so the packaged app never loads them.
Requests that need the app stopped (restart today; worktree switch and data
actions later) go to the dev supervisor through `desktop.dev_supervisor`.

Vocabulary: `GLOSSARY.md`, "Development".
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Longer than the supervisor can be busy stopping the app (STOP_TIMEOUT_SECONDS).
CONFIRM_TIMEOUT_SECONDS = 15.0
_CONFIRM_POLL_SECONDS = 0.1
_NO_SUPERVISOR = "The dev supervisor is not running; start the app with `python -m desktop.app --dev`."


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _git_status(repo_root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain=v2", "--branch"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=True,
    ).stdout


def parse_git_status(porcelain: str) -> dict[str, Any]:
    """Branch, short commit and dirty state from `git status --porcelain=v2 --branch`.

    A detached HEAD has no branch and an unborn branch has no commit; both stay None.
    """
    branch = commit = None
    dirty = False
    for line in porcelain.splitlines():
        if line.startswith("# branch.oid "):
            oid = line.removeprefix("# branch.oid ")
            commit = None if oid.startswith("(") else oid[:7]
        elif line.startswith("# branch.head "):
            head = line.removeprefix("# branch.head ")
            branch = None if head.startswith("(") else head
        elif line and not line.startswith("#"):
            dirty = True  # tracked change or untracked file
    return {"branch": branch, "commit": commit, "dirty": dirty}


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(left.resolve()) == os.path.normcase(right.resolve())


class DevBridgeMixin:
    @staticmethod
    def _dev_refusal() -> dict[str, Any] | None:
        """The blocked response of the packaged app; None in source mode."""
        if not getattr(sys, "frozen", False):
            return None
        message = "Dev tools are available only in dev mode (the app run from source with --dev)."
        return {
            "ok": False,
            "status": "blocked",
            "error": message,
            "status_reason_code": "dev_mode_only",
            "status_reason_message": message,
            "is_retry_allowed": False,
        }

    @staticmethod
    def _dev_control_dir() -> Path | None:
        from desktop import dev_supervisor  # noqa: PLC0415 - source-mode dev tooling

        value = os.environ.get(dev_supervisor.CONTROL_DIR_ENV)
        return Path(value) if value else None

    def dev_get_context(self, params=None) -> dict:
        """What this dev mode window is running: code, dev data and restart state."""
        refusal = self._dev_refusal()
        if refusal:
            return refusal
        try:
            from desktop import dev_data, dev_supervisor  # noqa: PLC0415

            repo_root = _repo_root()
            main = dev_data.main_checkout(repo_root)
            resolved = dev_data.resolve(repo_root, main=main)
            data_path = Path(os.environ.get("CVM_DATA_DIR") or resolved.data_root)
            if self._using_release_data_dir():
                data_mode = "installed-app"
            elif _same_path(data_path, resolved.data_root):
                data_mode = resolved.mode
            else:
                data_mode = "custom"  # explicit CVM_DATA_DIR

            git: dict[str, Any] = {"branch": None, "commit": None, "dirty": None}
            git_error = None
            try:
                git = parse_git_status(_git_status(repo_root))
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                git_error = str(exc)

            control_dir = self._dev_control_dir()
            status = dev_supervisor.read_status(control_dir) if control_dir else {}
            return {
                "ok": True,
                "worktree": repo_root.name,
                "worktree_path": str(repo_root),
                "is_main_checkout": _same_path(main, repo_root),
                **git,
                "git_error": git_error,
                "data_mode": data_mode,
                "data_path": str(data_path),
                "supervised": control_dir is not None,
                "auto_restart": status.get("auto_restart"),
                "pending_changes": status.get("pending_changes"),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _dev_request(self, action: str, **params: Any) -> dict[str, Any] | None:
        """Queue a request for the dev supervisor; return the failure response, if any."""
        refusal = self._dev_refusal()
        if refusal:
            return refusal
        control_dir = self._dev_control_dir()
        if control_dir is None:
            return {"ok": False, "error": _NO_SUPERVISOR}
        try:
            from desktop import dev_supervisor  # noqa: PLC0415

            dev_supervisor.send_request(control_dir, action, **params)
        except OSError as exc:
            return {"ok": False, "error": f"Could not reach the dev supervisor: {exc}"}
        return None

    def dev_restart(self, params=None) -> dict:
        """Ask the dev supervisor to restart the app; the window closes right after."""
        return self._dev_request("restart") or {"ok": True}

    def dev_set_auto_restart(self, params=None) -> dict:
        """Turn automatic restart on Python changes on or off; returns the confirmed state."""
        enabled = (params or {}).get("enabled")
        if not isinstance(enabled, bool):
            return {"ok": False, "error": "`enabled` must be true or false."}
        failure = self._dev_request("set_auto_restart", enabled=enabled)
        if failure:
            return failure
        from desktop import dev_supervisor  # noqa: PLC0415

        control_dir = self._dev_control_dir()
        deadline = time.monotonic() + CONFIRM_TIMEOUT_SECONDS
        while True:
            if control_dir and dev_supervisor.read_status(control_dir).get("auto_restart") is enabled:
                return {"ok": True, "auto_restart": enabled}
            if time.monotonic() >= deadline:
                return {"ok": False, "error": "The dev supervisor did not confirm the change."}
            time.sleep(_CONFIRM_POLL_SECONDS)
