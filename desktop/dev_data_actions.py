"""Dev data actions of the dev panel: move to backup, restore backup, delete permanently.

Source-mode dev tooling only; the packaged app never calls this module. The dev
supervisor runs `perform` with the app stopped, so no database handle is open.
The dev bridge calls `describe`, `refusal` and `check` to show sizes and refuse
early, before the window closes.

Targets: the database (`<data root>/db`), the downloaded CVM files (`input`; the
shared folder for isolated dev data) and everything (the data root). Each target
has one dev data backup slot, `<root>.backup/<target>`, next to the root that
holds it; a newer backup deletes the older one. Every step is a rename on the
same volume, so a target is either untouched or fully moved, and a failed rename
puts back what was already moved.

Nothing here touches installed-app data: `refusal` accepts only the dev data
folder of a git checkout (`<checkout>/data/dev-runtime`) that does not overlap
`Documents\\CVMAnalytics`.

Vocabulary: `GLOSSARY.md`, "Development".
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Mapping

from desktop.dev_data import FULL_COPY, ISOLATED, SHARED, DevData

TARGETS = {"db": "Database", "input": "Downloaded CVM files", "all": "Everything"}
OPERATIONS = ("backup", "restore", "delete")
_RENAME_ATTEMPTS = 3  # a virus scanner or indexer can hold a just-closed file for a moment
_RENAME_RETRY_SECONDS = 0.5


class ActionError(Exception):
    """The action did not run or was rolled back; the message says what failed."""


def _norm(path: Path) -> Path:
    return Path(os.path.normcase(path.resolve()))


def _same_path(left: Path, right: Path) -> bool:
    return _norm(left) == _norm(right)


def _overlaps(left: Path, right: Path) -> bool:
    left, right = _norm(left), _norm(right)
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _installed_app_roots(environ: Mapping[str, str]) -> list[Path]:
    """Data roots of the installed app (see `_user_data_root` in `desktop/app.py`)."""
    roots = [Path(environ["CVMANALYTICS_DATA_DIR"])] if environ.get("CVMANALYTICS_DATA_DIR") else []
    if environ.get("USERPROFILE"):
        roots.append(Path(environ["USERPROFILE"]) / "Documents" / "CVMAnalytics")
    if environ.get("LOCALAPPDATA"):
        roots.append(Path(environ["LOCALAPPDATA"]) / "CVMAnalytics")  # pre-Documents root, updater staging
    return roots


def targets(dev: DevData) -> dict[str, tuple[Path, Path]]:
    """Each target's path and the data root that holds it."""
    input_root = dev.shared_root if dev.mode == ISOLATED else dev.data_root
    return {
        "db": (dev.data_root / "db", dev.data_root),
        "input": (input_root / "input", input_root),
        "all": (dev.data_root, dev.data_root),
    }


def backup_slot(root: Path, target: str) -> Path:
    return root.parent / f"{root.name}.backup" / target


def size_of(path: Path) -> int | None:
    """Total bytes of the files under `path`; None when it does not exist."""
    if not path.exists():
        return None
    if path.is_file():
        return path.stat().st_size
    total = 0
    for directory, _subdirectories, files in os.walk(path):
        for name in files:
            try:
                total += (Path(directory) / name).stat().st_size
            except OSError:  # deleted or locked meanwhile
                pass
    return total


def describe(dev: DevData) -> list[dict[str, Any]]:
    """Path, size, shared flag and backup of every target, for the dev panel."""
    described = []
    for target, (path, root) in targets(dev).items():
        slot = backup_slot(root, target)
        described.append(
            {
                "target": target,
                "path": str(path),
                "exists": path.exists(),
                "size_bytes": size_of(path),
                "shared": _same_path(root, dev.shared_root),
                "backup_path": str(slot),
                "backup_exists": slot.exists(),
                "backup_size_bytes": size_of(slot),
            }
        )
    return described


def refusal(dev: DevData, environ: Mapping[str, str]) -> str | None:
    """Why data actions are unavailable for this dev data, or None when they are allowed."""
    if getattr(sys, "frozen", False):
        return "Dev data actions are available only in dev mode (the app run from source with --dev)."
    if environ.get("CVMANALYTICS_USE_RELEASE_DATA", "").strip().lower() in {"1", "true", "yes"}:
        return (
            "Dev mode uses installed-app data (CVMANALYTICS_USE_RELEASE_DATA). "
            "Data actions never touch Documents\\CVMAnalytics."
        )
    custom = environ.get("CVM_DATA_DIR")
    if custom and not _same_path(Path(custom), dev.data_root):
        return (
            f"A custom data directory is set (CVM_DATA_DIR={custom}). Data actions work only on "
            "shared or isolated dev data; launch dev mode without CVM_DATA_DIR to use them."
        )
    if dev.mode not in (SHARED, ISOLATED, FULL_COPY):
        return f"Unknown dev data mode {dev.mode!r}."
    if dev.mode == SHARED and not _same_path(dev.data_root, dev.shared_root):
        return "Shared dev data must be the main checkout's dev data folder."
    for root in (dev.data_root, dev.shared_root):
        for installed in _installed_app_roots(environ):
            if _overlaps(root, installed):
                return f"{root} is or overlaps installed-app data ({installed}). Data actions never touch it."
        if not (root.name == "dev-runtime" and root.parent.name == "data" and (root.parent.parent / ".git").exists()):
            return f"{root} is not the dev data folder of a git checkout (<checkout>\\data\\dev-runtime)."
    return None


def _lock_holder(root: Path, own_pid: int) -> int | None:
    """PID of another live process holding the runtime lock of `root`, if any."""
    from desktop import lockfile  # noqa: PLC0415 - standard library only

    lock = lockfile._read_lock_file(root / lockfile._LOCK_FILENAME) or {}
    pid = lock.get("pid") if isinstance(lock, dict) else None
    if isinstance(pid, int) and pid != own_pid and lockfile._pid_alive(pid):
        return pid
    return None


def check(dev: DevData, operation: Any, target: Any, *, own_pid: int) -> str | None:
    """Why this action cannot run now (bad request, data in use, nothing to act on), or None."""
    if operation not in OPERATIONS:
        return f"Unknown data action {operation!r}; expected one of {', '.join(OPERATIONS)}."
    if target not in TARGETS:
        return f"Unknown data target {target!r}; expected one of {', '.join(TARGETS)}."
    path, root = targets(dev)[target]
    holder = _lock_holder(root, own_pid)
    if holder is not None:
        return (
            f"{root} is in use by another CVMAnalytics process (PID {holder}). "
            "Close that app or dev mode window first."
        )
    if operation == "restore":
        slot = backup_slot(root, target)
        return None if slot.exists() else f"There is no {TARGETS[target]} backup at {slot}."
    return None if path.exists() else f"{path} does not exist; there is nothing to {'delete' if operation == 'delete' else 'move'}."


# --- File operations: renames on one volume, rolled back on failure -----------


def _rename(source: Path, destination: Path) -> None:
    for attempt in range(1, _RENAME_ATTEMPTS + 1):
        try:
            os.rename(source, destination)  # never replaces: every destination is new
            return
        except PermissionError:
            if attempt == _RENAME_ATTEMPTS:
                raise
            time.sleep(_RENAME_RETRY_SECONDS)


def _to_trash(path: Path, slot_dir: Path) -> Path:
    """Move `path` out of the way, next to the backup slots, before it is removed."""
    trash = slot_dir / f".trash-{path.name}-{time.time_ns()}"
    try:
        slot_dir.mkdir(parents=True, exist_ok=True)
        _rename(path, trash)
    except OSError as error:
        raise ActionError(f"Could not move {path} out of the way: {error}. Nothing was changed.") from error
    return trash


def _remove(path: Path | None) -> str | None:
    """Remove data already out of the app's way; a leftover is a warning, not a failure."""
    if path is None:
        return None
    try:
        shutil.rmtree(path)
    except OSError as error:
        return f"Could not remove {path} ({error}); delete it by hand."
    return None


def _put_back(moved: Path, original: Path, error: OSError, what: str) -> ActionError:
    """Undo the first rename after the second failed; say where data is if that fails too."""
    try:
        _rename(moved, original)
    except OSError as rollback_error:
        return ActionError(
            f"Could not {what}: {error}. Putting the data back also failed ({rollback_error}): "
            f"it is at {moved}; move it back to {original} by hand."
        )
    return ActionError(f"Could not {what}: {error}. Nothing was changed.")


def move_to_backup(current: Path, slot: Path) -> str | None:
    """Rename `current` into the backup slot; the older backup is deleted. Returns a warning."""
    older = _to_trash(slot, slot.parent) if slot.exists() else None
    try:
        slot.parent.mkdir(parents=True, exist_ok=True)
        _rename(current, slot)
    except OSError as error:
        what = f"move {current} to {slot}"
        if older is None:
            raise ActionError(f"Could not {what}: {error}. Nothing was changed.") from error
        raise _put_back(older, slot, error, what) from error
    return _remove(older)


def restore_backup(current: Path, slot: Path) -> str | None:
    """Replace `current` with the backup; current data is deleted. Returns a warning."""
    replaced = _to_trash(current, slot.parent) if current.exists() else None
    try:
        current.parent.mkdir(parents=True, exist_ok=True)
        _rename(slot, current)
    except OSError as error:
        what = f"restore {slot} to {current}"
        if replaced is None:
            raise ActionError(f"Could not {what}: {error}. Nothing was changed.") from error
        raise _put_back(replaced, current, error, what) from error
    return _remove(replaced)


def delete_permanently(current: Path, slot: Path) -> str | None:
    """Remove `current`: renamed away first, so the app never sees half a folder. Returns a warning."""
    return _remove(_to_trash(current, slot.parent))


_DONE = {"backup": "Moved {label} to backup", "restore": "Restored the {label} backup", "delete": "Deleted {label} permanently"}


def perform(request: Mapping[str, Any], environ: Mapping[str, str] = os.environ) -> dict[str, Any]:
    """Run one data action from the supervisor; the result says what happened.

    The request carries the dev data the app resolved; it is validated again
    here because the request channel is a plain folder.
    """
    operation, target = request.get("operation"), request.get("target")
    result: dict[str, Any] = {"operation": operation, "target": target}
    try:
        dev = DevData(str(request["mode"]), Path(request["data_root"]), Path(request["shared_root"]))
        reason = refusal(dev, environ) or check(dev, operation, target, own_pid=os.getpid())
        if reason:
            raise ActionError(reason)
        path, root = targets(dev)[target]
        slot = backup_slot(root, target)
        action = {"backup": move_to_backup, "restore": restore_backup, "delete": delete_permanently}[operation]
        warning = action(path, slot)
    except (ActionError, OSError, KeyError, TypeError) as error:
        message = error.args[0] if isinstance(error, ActionError) else f"{type(error).__name__}: {error}"
        return {**result, "ok": False, "message": f"Data action failed: {message}"}
    message = _DONE[operation].format(label=TARGETS[target]) + f" ({path})."
    return {**result, "ok": True, "message": message + (f" {warning}" if warning else "")}
