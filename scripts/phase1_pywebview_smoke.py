"""Phase 1 end-to-end smoke / dev runner.

Spawns:
  - `vite` dev (apps/desktop-web) on port 5173
  - pywebview window on http://127.0.0.1:5173/

The pywebview window receives the same CVMBridge instance the packaged app
uses, so window.pywebview.api is the real production bridge.

Modes:
  Default (automated)
    Window auto-closes after --timeout seconds (default 12). Bridge tap
    prints ping / health / companies / detail / statements. CI-friendly.

  Manual / interactive
    Pass --manual or --no-auto-close. Window stays open until you close it
    yourself; bridge tap still prints at startup.

Examples:
  python scripts/phase1_pywebview_smoke.py
  python scripts/phase1_pywebview_smoke.py --timeout 30
  python scripts/phase1_pywebview_smoke.py --manual
  python scripts/phase1_pywebview_smoke.py --no-auto-close
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from desktop.bridge import CVMBridge  # noqa: E402


VITE_PORT = 5173
VITE_DIR = REPO_ROOT / "apps" / "desktop-web"
DEFAULT_AUTO_CLOSE_SECONDS = 12


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _wait_for_port(port: int, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_open(port):
            return True
        time.sleep(0.2)
    return False


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="phase1_pywebview_smoke",
        description=(
            "Launch pywebview against the Vite dev server with the real "
            "CVMBridge wired in. Use --manual to keep the window open for "
            "exploration."
        ),
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Keep the window open until the user closes it. Disables auto-close.",
    )
    parser.add_argument(
        "--no-auto-close",
        action="store_true",
        help="Alias for --manual.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_AUTO_CLOSE_SECONDS,
        metavar="SECONDS",
        help=(
            f"Seconds before automatic window close. Ignored when --manual "
            f"is set. Default: {DEFAULT_AUTO_CLOSE_SECONDS}."
        ),
    )
    return parser.parse_args(argv)


def _bridge_tap(bridge: CVMBridge) -> None:
    """Independent verification of the Python side. Runs in a daemon thread."""
    time.sleep(4)  # let pywebview inject api
    try:
        print(f"[smoke] bridge.ping: {bridge.ping()}")
        health = bridge.get_health()
        print(
            f"[smoke] bridge.get_health: status={health.get('status')} "
            f"dialect={health.get('database_dialect')}"
        )
        page = bridge.get_companies({"page": 1, "page_size": 3})
        items = page.get("items", [])
        total = page.get("pagination", {}).get("total_items")
        first = items[0] if items else None
        print(
            f"[smoke] bridge.get_companies: total={total} "
            f"first={first['company_name'] if first else 'none'}"
        )
        if first:
            cd_cvm = first["cd_cvm"]
            info = bridge.get_company_info({"cd_cvm": cd_cvm})
            print(
                f"[smoke] bridge.get_company_info({cd_cvm}): "
                f"name={info.get('company_name')} "
                f"latest_year={info.get('latest_readable_year')}"
            )
            years_resp = bridge.get_company_years({"cd_cvm": cd_cvm})
            years = years_resp.get("years", [])
            print(f"[smoke] bridge.get_company_years({cd_cvm}): {years}")
            if years:
                selected = sorted(years)[-3:]
                kpis = bridge.get_company_kpis(
                    {"cd_cvm": cd_cvm, "years": selected}
                )
                annual = kpis.get("annual", {})
                print(
                    f"[smoke] bridge.get_company_kpis({cd_cvm}, {selected}): "
                    f"rows={len(annual.get('rows', []))} "
                    f"columns={len(annual.get('columns', []))}"
                )
                statement = bridge.get_company_statement(
                    {"cd_cvm": cd_cvm, "years": selected, "stmt": "DRE"}
                )
                table = statement.get("table", {})
                print(
                    f"[smoke] bridge.get_company_statement({cd_cvm}, {selected}, DRE): "
                    f"rows={len(table.get('rows', []))} "
                    f"columns={len(table.get('columns', []))}"
                )
    except Exception as exc:
        print(f"[smoke] bridge tap error: {exc!r}")


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    manual = args.manual or args.no_auto_close
    timeout = max(1, int(args.timeout))

    npm = "npm.cmd" if os.name == "nt" else "npm"
    print(f"[smoke] launching vite dev in {VITE_DIR}")
    vite = subprocess.Popen(
        [npm, "run", "dev"],
        cwd=str(VITE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if not _wait_for_port(VITE_PORT, timeout=30):
        vite.terminate()
        sys.exit(f"[smoke] vite did not bind 127.0.0.1:{VITE_PORT} in 30s")

    vite_url = f"http://127.0.0.1:{VITE_PORT}"
    print(f"[smoke] vite listening on {vite_url}")

    if manual:
        print("[smoke] mode: manual (window stays open until you close it)")
        print(f"[smoke] open in a browser as well: {vite_url}")
        print("[smoke] close the pywebview window to exit.")
    else:
        print(f"[smoke] mode: automated (auto-close after {timeout}s)")
        print(f"[smoke] pass --manual to keep the window open for exploration")

    import webview  # noqa: PLC0415

    bridge = CVMBridge()
    window = webview.create_window(
        "Phase 1 smoke",
        url=vite_url,
        js_api=bridge,
        width=1200,
        height=820,
    )

    if not manual:
        def _autoclose() -> None:
            time.sleep(timeout)
            try:
                print(f"[smoke] auto-closing window after {timeout}s")
                window.destroy()
            except Exception:
                pass

        threading.Thread(target=_autoclose, daemon=True).start()

    threading.Thread(target=_bridge_tap, args=(bridge,), daemon=True).start()

    try:
        webview.start()
    finally:
        vite.terminate()
        try:
            vite.wait(timeout=5)
        except subprocess.TimeoutExpired:
            vite.kill()


if __name__ == "__main__":
    main()
