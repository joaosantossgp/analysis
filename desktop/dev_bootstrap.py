"""Provision the source-mode development environment before runtime imports."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


_MINIMUM_PYTHON = (3, 11)
_PYTHON_STAMP = ".cvmanalytics-dev-bootstrap.json"
_FRONTEND_STAMP = ".cvmanalytics-dev-bootstrap.json"
_REPAIR_FLAG = "--repair-dev-environment"
_REBUILD_FLAG = "--rebuild-dev-environment"


class BootstrapError(RuntimeError):
    """Raised when a declared development dependency cannot be provisioned."""

    def __init__(self, command: Sequence[str], returncode: int, output: str) -> None:
        rendered_command = subprocess.list2cmdline([str(part) for part in command])
        super().__init__(
            "CVMAnalytics development bootstrap failed.\n"
            f"Command: {rendered_command}\n"
            f"Exit code: {returncode}\n"
            f"Output:\n{output.strip() or '(no output)'}\n\n"
            "After resolving the underlying issue, run:\n"
            "  python -m desktop.app --repair-dev-environment --dev"
        )
        self.command = [str(part) for part in command]
        self.returncode = returncode
        self.output = output


def repository_root() -> Path:
    return Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _is_windows() -> bool:
    return os.name == "nt"


def venv_python(repo_root: Path) -> Path:
    if _is_windows():
        return repo_root / ".venv" / "Scripts" / "python.exe"
    return repo_root / ".venv" / "bin" / "python"


def python_stamp_path(repo_root: Path) -> Path:
    return repo_root / ".venv" / _PYTHON_STAMP


def frontend_stamp_path(repo_root: Path) -> Path:
    return repo_root / "apps" / "desktop-web" / "node_modules" / _FRONTEND_STAMP


def _fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_python() -> str:
    return os.environ.get("CVMANALYTICS_DEV_BOOTSTRAP_BASE_PYTHON", sys.executable)


def python_stamp(repo_root: Path, interpreter: str) -> dict[str, object]:
    requirements = repo_root / "requirements.txt"
    return {
        "requirements_sha256": _fingerprint(requirements),
        "source_python": str(Path(interpreter)),
        "python_version": list(sys.version_info[:3]),
    }


def write_python_stamp(repo_root: Path, stamp: dict[str, object]) -> None:
    path = python_stamp_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stamp, sort_keys=True) + "\n", encoding="utf-8")


def write_frontend_stamp(repo_root: Path) -> None:
    path = frontend_stamp_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    lockfile = repo_root / "apps" / "desktop-web" / "package-lock.json"
    path.write_text(json.dumps({"lockfile_sha256": _fingerprint(lockfile)}) + "\n", encoding="utf-8")


def _read_stamp(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _run_checked(command: Sequence[str], *, cwd: Path | None = None) -> None:
    try:
        result = subprocess.run(
            [str(part) for part in command],
            cwd=str(cwd) if cwd is not None else None,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise BootstrapError(command, getattr(exc, "winerror", 1) or 1, str(exc)) from exc
    if result.returncode != 0:
        raise BootstrapError(command, result.returncode, f"{result.stdout}\n{result.stderr}")


def _validate_python_version() -> None:
    if sys.version_info >= _MINIMUM_PYTHON:
        return
    required = ".".join(map(str, _MINIMUM_PYTHON))
    actual = ".".join(map(str, sys.version_info[:3]))
    raise BootstrapError([sys.executable, "--version"], 1, f"Python {required}+ is required; found {actual}.")


def _bootstrap_flags(argv: Sequence[str]) -> tuple[bool, bool]:
    return _REPAIR_FLAG in argv, _REBUILD_FLAG in argv


def _strip_bootstrap_flags(argv: Sequence[str]) -> list[str]:
    return [arg for arg in argv if arg not in {_REPAIR_FLAG, _REBUILD_FLAG}]


def _stamp_matches(path: Path, expected: dict[str, object]) -> bool:
    return _read_stamp(path) == expected


def ensure_source_environment(argv: Sequence[str], *, repo_root: Path | None = None) -> list[str]:
    """Create/synchronize `.venv` from root requirements when its stamp is stale."""
    root = repo_root or repository_root()
    _validate_python_version()
    repair, rebuild = _bootstrap_flags(argv)
    venv_dir = root / ".venv"
    target_python = venv_python(root)
    source_python = _source_python()
    expected_stamp = python_stamp(root, source_python)

    if rebuild and venv_dir.exists():
        shutil.rmtree(venv_dir)

    if target_python.exists() and not repair and _stamp_matches(python_stamp_path(root), expected_stamp):
        return _strip_bootstrap_flags(argv)

    if not target_python.exists():
        _run_checked([source_python, "-m", "venv", "--copies", str(venv_dir)])
    if not target_python.exists():
        raise BootstrapError(
            [source_python, "-m", "venv", "--copies", str(venv_dir)],
            1,
            f"The virtual-environment interpreter was not created at {target_python}.",
        )

    _run_checked([str(target_python), "-m", "pip", "install", "-r", str(root / "requirements.txt")])
    write_python_stamp(root, expected_stamp)
    return _strip_bootstrap_flags(argv)


def _node_version() -> tuple[int, int, int]:
    command = ["node", "--version"]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        raise BootstrapError(command, getattr(exc, "winerror", 1) or 1, "Node.js 22+ is required for --dev. " + str(exc)) from exc
    output = f"{result.stdout}\n{result.stderr}".strip()
    if result.returncode != 0 or not output.startswith("v"):
        raise BootstrapError(command, result.returncode or 1, output or "Node.js 22+ is required for --dev.")
    try:
        major, minor, patch = (int(part) for part in output[1:].split(".", 2))
    except ValueError as exc:
        raise BootstrapError(command, 1, f"Could not parse Node.js version: {output}") from exc
    if (major, minor, patch) < (22, 0, 0):
        raise BootstrapError(command, 1, f"Node.js 22+ is required for --dev; found {output}.")
    return major, minor, patch


def ensure_dev_frontend(argv: Sequence[str], *, repo_root: Path | None = None) -> None:
    """Synchronize Vite dependencies from the committed lockfile for `--dev`."""
    if "--dev" not in argv:
        return
    root = repo_root or repository_root()
    frontend = root / "apps" / "desktop-web"
    lockfile = frontend / "package-lock.json"
    if not lockfile.exists():
        raise BootstrapError(["npm", "ci"], 1, f"Missing frontend lockfile: {lockfile}")
    _node_version()
    repair, _ = _bootstrap_flags(argv)
    expected = {"lockfile_sha256": _fingerprint(lockfile)}
    if not repair and _stamp_matches(frontend_stamp_path(root), expected):
        return
    _run_checked(["npm.cmd" if _is_windows() else "npm", "ci"], cwd=frontend)
    write_frontend_stamp(root)


def in_project_venv(repo_root: Path, executable: str) -> bool:
    target = venv_python(repo_root)
    return os.path.normcase(os.path.abspath(executable)) == os.path.normcase(os.path.abspath(target))


def _relaunch_in_venv(command: Sequence[str]) -> None:
    """Run the target interpreter and return its exit status to the source shell.

    ``os.execv`` is unreliable for this Python/module handoff on Windows. A
    normal child process preserves the exact `-m desktop.app` command line and
    still keeps the system interpreter isolated from project dependencies.
    """
    environment = os.environ.copy()
    environment.setdefault("CVMANALYTICS_DEV_BOOTSTRAP_BASE_PYTHON", sys.executable)
    try:
        completed = subprocess.run([str(part) for part in command], env=environment, check=False)
    except OSError as exc:
        raise BootstrapError(command, getattr(exc, "winerror", 1) or 1, str(exc)) from exc
    raise SystemExit(completed.returncode)


def bootstrap_and_reexec_if_needed(argv: Sequence[str], *, repo_root: Path | None = None) -> list[str]:
    """Provision source dependencies then launch the app through `.venv` Python."""
    if is_frozen():
        return list(argv)
    root = repo_root or repository_root()
    clean_argv = ensure_source_environment(argv, repo_root=root)
    ensure_dev_frontend(argv, repo_root=root)
    target_python = venv_python(root)
    if not in_project_venv(root, sys.executable):
        _relaunch_in_venv([str(target_python), "-m", "desktop.app", *clean_argv])
    return clean_argv
