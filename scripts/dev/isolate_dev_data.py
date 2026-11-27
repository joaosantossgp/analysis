"""Turn this git worktree into a data-sensitive worktree with isolated dev data.

Usage (from the worktree, with its environment):
  .\\.venv\\Scripts\\python.exe scripts/dev/isolate_dev_data.py              # own databases, shared downloads
  .\\.venv\\Scripts\\python.exe scripts/dev/isolate_dev_data.py --full-copy  # own copy of everything
  .\\.venv\\Scripts\\python.exe scripts/dev/isolate_dev_data.py --force      # replace an existing own copy

Copies from the shared dev data of the main checkout (read only, WAL-safe for
the databases), then writes the git-ignored marker `.dev-data-isolated`. Dev
mode picks the marker up on its next start. Refuses to run on the main checkout.
To go back to shared dev data, delete the marker.

Rule for when to isolate: AGENTS.md, "Dev data in worktrees".
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from desktop import dev_data  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--full-copy",
        action="store_true",
        help="also copy the downloaded CVM files (about 2 GB); for work that changes their format or location",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace dev data this worktree already holds with a fresh copy",
    )
    args = parser.parse_args(argv)

    try:
        result = dev_data.isolate(REPO_ROOT, full_copy=args.full_copy, force=args.force)
    except dev_data.IsolationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    downloads = result.data_root if result.mode == dev_data.FULL_COPY else result.shared_root
    print(f"Dev data mode: {result.mode} (marker: {REPO_ROOT / dev_data.MARKER_NAME})")
    print(f"Data root:     {result.data_root}")
    print(f"Downloads:     {downloads / 'input'}")
    if not (result.data_root / "db" / "cvm_financials.db").exists():
        print("Note: shared dev data has no database yet; this worktree starts with an empty one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
