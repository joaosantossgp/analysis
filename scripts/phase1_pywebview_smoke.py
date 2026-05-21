"""Phase 1 end-to-end smoke: launch pywebview pointed at the Vite dev server.

Spawns:
  - `vite` dev (apps/desktop-web) on port 5173
  - pywebview window on http://127.0.0.1:5173/

The pywebview window is given the same CVMBridge instance the packaged app
uses, so window.pywebview.api is the real production bridge. The script
exits after a short timeout — the goal is to prove the wiring, not to
keep a window open.

Run with:
  python -m scripts.phase1_pywebview_smoke
or:
  python scripts/phase1_pywebview_smoke.py
"""
from __future__ import annotations

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


def main() -> None:
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
    print(f"[smoke] vite listening on 127.0.0.1:{VITE_PORT}")

    import webview  # noqa: PLC0415

    bridge = CVMBridge()
    window = webview.create_window(
        "Phase 1 smoke",
        url=f"http://127.0.0.1:{VITE_PORT}",
        js_api=bridge,
        width=900,
        height=700,
    )

    # Background timer to close the window after 12 seconds — keeps the
    # smoke unattended. Long enough for TanStack Query to issue both the
    # health and companies fetches end-to-end.
    def _autoclose() -> None:
        time.sleep(12)
        try:
            print("[smoke] auto-closing window")
            window.destroy()
        except Exception:
            pass

    # Background bridge-tap: independent verification that the Python side
    # is reachable. Mirrors what the React app does via window.pywebview.api.
    def _bridge_tap() -> None:
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
        except Exception as exc:
            print(f"[smoke] bridge tap error: {exc!r}")

    threading.Thread(target=_autoclose, daemon=True).start()
    threading.Thread(target=_bridge_tap, daemon=True).start()
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
