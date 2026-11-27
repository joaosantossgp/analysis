"""Dev data root of a source checkout: shared by default, isolated by marker.

Source-mode dev tooling only; the packaged app never calls this module.

Every git worktree uses the shared dev data of the main checkout
(`<main checkout>/data/dev-runtime`). A git-ignored marker file at the root of a
worktree makes it a data-sensitive worktree with isolated dev data:

- `isolated`: its own copy of the databases; downloaded CVM files are still
  read from the shared folder.
- `full-copy`: its own copy of everything.

Vocabulary: `GLOSSARY.md`, "Development".
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

MARKER_NAME = ".dev-data-isolated"
SHARED = "shared"
ISOLATED = "isolated"
FULL_COPY = "full-copy"


class IsolationError(Exception):
    """The worktree cannot be given isolated dev data; the message says why."""


@dataclass(frozen=True)
class DevData:
    mode: str  # SHARED | ISOLATED | FULL_COPY
    data_root: Path  # where this checkout reads and writes dev data
    shared_root: Path  # the main checkout's dev data folder


def dev_data_root(checkout: Path) -> Path:
    return checkout / "data" / "dev-runtime"


def parse_main_checkout(porcelain: str) -> Path | None:
    """The first entry of `git worktree list --porcelain` is the main checkout."""
    for line in porcelain.splitlines():
        if line.startswith("worktree "):
            return Path(line.removeprefix("worktree "))
    return None


def main_checkout(repo_root: Path) -> Path:
    """The main checkout of `repo_root`; `repo_root` itself when git cannot answer."""
    try:
        listing = subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return repo_root
    return parse_main_checkout(listing) or repo_root


def _same_checkout(left: Path, right: Path) -> bool:
    return os.path.normcase(left.resolve()) == os.path.normcase(right.resolve())


def _marker_mode(repo_root: Path) -> str | None:
    try:
        text = (repo_root / MARKER_NAME).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    # Any other content still isolates the database: the safe reading of a marker.
    return FULL_COPY if text == FULL_COPY else ISOLATED


def resolve(repo_root: Path, *, main: Path | None = None) -> DevData:
    """Resolve the dev data of a checkout. The main checkout always owns shared dev data."""
    main = main or main_checkout(repo_root)
    shared_root = dev_data_root(main)
    mode = None if _same_checkout(main, repo_root) else _marker_mode(repo_root)
    if mode is None:
        return DevData(SHARED, shared_root, shared_root)
    return DevData(mode, dev_data_root(repo_root), shared_root)


def isolate(
    repo_root: Path,
    *,
    full_copy: bool = False,
    force: bool = False,
    main: Path | None = None,
) -> DevData:
    """Give a worktree isolated dev data: copy from shared dev data, then write the marker.

    Shared dev data is only read. The marker is written last, so a failed copy
    leaves the worktree on shared dev data.
    """
    main = main or main_checkout(repo_root)
    if _same_checkout(main, repo_root):
        raise IsolationError(
            f"{repo_root} is the main checkout (or git could not list its worktrees). "
            "The main checkout owns shared dev data and cannot be isolated; run this from a git worktree."
        )
    mode = FULL_COPY if full_copy else ISOLATED
    shared_root, own_root = dev_data_root(main), dev_data_root(repo_root)
    source, target = (shared_root, own_root) if full_copy else (shared_root / "db", own_root / "db")

    if target.is_dir() and any(target.iterdir()):
        if not force:
            raise IsolationError(
                f"{target} already holds dev data of this worktree. "
                "Pass --force to replace it with a fresh copy of shared dev data."
            )
        shutil.rmtree(target)

    if source.is_dir():
        # Imported here: the launcher module pulls in the whole app runtime.
        from desktop.app import _wal_safe_copy_sqlite  # noqa: PLC0415

        def copy_file(src: str, dst: str) -> None:
            if src.endswith(".db"):
                _wal_safe_copy_sqlite(Path(src), Path(dst))
            else:
                shutil.copy2(src, dst)

        shutil.copytree(
            source,
            target,
            # The WAL-safe copy already folds -wal/-shm into each database copy.
            ignore=shutil.ignore_patterns("runtime.lock", "*-wal", "*-shm"),
            copy_function=copy_file,
            dirs_exist_ok=True,
        )

    (repo_root / MARKER_NAME).write_text(mode + "\n", encoding="utf-8")
    return DevData(mode, own_root, shared_root)
