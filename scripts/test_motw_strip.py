"""Sandbox test for _strip_motw_from_bundle.

Creates a temp directory with one DLL, applies a Zone.Identifier ADS to
it via subprocess (PowerShell Set-Content), runs the strip function in
bundled-simulation mode, and verifies the ADS is gone.
"""
from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def has_zone_identifier(file_path: Path) -> bool:
    ads = str(file_path) + ":Zone.Identifier"
    try:
        with open(ads, "rb"):
            return True
    except (OSError, FileNotFoundError):
        return False


def main() -> int:
    sandbox = Path(tempfile.mkdtemp(prefix="motw_strip_"))
    try:
        # Create test DLL (copy a real one)
        source_dll = Path("dist/CVMAnalytics/_internal/pythonnet/runtime/Python.Runtime.dll")
        if not source_dll.exists():
            print(f"FAIL: source DLL missing at {source_dll}")
            return 2
        test_dll = sandbox / "Python.Runtime.dll"
        shutil.copy2(source_dll, test_dll)
        nested_dll = sandbox / "_internal" / "node.dll"
        nested_dll.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_dll, nested_dll)
        non_dll = sandbox / "readme.txt"
        non_dll.write_text("not a binary")

        # Apply Zone.Identifier ADS via PowerShell Set-Content
        for f in (test_dll, nested_dll, non_dll):
            ads = f"{f}:Zone.Identifier"
            subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    f"Set-Content -LiteralPath '{ads}' -Value '[ZoneTransfer]`nZoneId=3' -Encoding utf8",
                ],
                check=True,
                capture_output=True,
            )

        # Sanity: ADS present on all 3
        before = {f.name: has_zone_identifier(f) for f in (test_dll, nested_dll, non_dll)}
        print(f"ADS before strip: {before}")
        if not all(before.values()):
            print("FAIL: setup did not apply ADS to all files")
            return 3

        # Patch desktop.app to point at sandbox
        import desktop.app as A
        importlib.reload(A)
        A._bundled = lambda: True
        A._bundle_dir = lambda: sandbox

        removed = A._strip_motw_from_bundle()
        print(f"streams removed: {removed}")

        # ADS should be gone from .dll files, untouched on .txt
        after = {f.name: has_zone_identifier(f) for f in (test_dll, nested_dll, non_dll)}
        print(f"ADS after strip: {after}")

        if after[test_dll.name]:
            print("FAIL: Python.Runtime.dll still has ADS")
            return 4
        if after[nested_dll.name]:
            print("FAIL: nested DLL still has ADS")
            return 5
        if not after[non_dll.name]:
            print("FAIL: .txt file should be untouched (we only strip DLL/EXE/PYD/NODE/PS1)")
            return 6

        # Files must still exist with unchanged content
        if test_dll.stat().st_size != source_dll.stat().st_size:
            print("FAIL: test DLL size changed")
            return 7

        print("PASS: MOTW stripped from .dll files, file bodies intact")

        # Re-run = idempotent (should remove 0 more)
        removed2 = A._strip_motw_from_bundle()
        print(f"streams removed on second pass: {removed2}")
        if removed2 != 0:
            print("FAIL: not idempotent")
            return 8

        print("PASS: idempotent")
        return 0
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
