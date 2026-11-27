"""Software update bridge methods extracted from desktop/bridge_api/status.py."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger("desktop.bridge")

class StatusUpdatesMixin:
    def _start_update_check(self) -> None:
        """Called from a daemon thread in app.py after window creation.

        Records the full status, so a failed check (offline) is remembered as
        "check_failed" instead of reading as "up to date".
        """
        try:
            self._get_software_update_status(force=True)
        except Exception:
            logger.exception("startup update check failed")

    def check_update(self, params=None) -> dict:
        with self._update_lock:
            info = self._update_info
            status = dict(self._latest_update_status or {})
        if not info:
            return self._sanitize_for_json({
                "available": False,
                "status": status.get("status") or "not_checked",
                "error": status.get("error"),
            })
        return self._sanitize_for_json({
            "available": True,
            "version": info["version"],
            "zip_url": info["zip_url"],
        })

    def apply_update(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("apply_update"))
        with self._update_lock:
            info = self._update_info
            if not info:
                return self._sanitize_for_json({"error": "no_update_available"})
            if self._update_progress.get("status") == "downloading":
                return self._sanitize_for_json({"error": "already_in_progress"})
            self._update_progress = {"status": "downloading", "percent": 0, "error": None}

        def _run() -> None:
            try:
                from desktop.updater import UpdateChecker, _log as _update_log  # noqa: PLC0415
                _update_log(
                    f"apply_update invoked: version={info.get('version')} "
                    f"tag={info.get('tag')} zip_url={info.get('zip_url')}"
                )
                checker = UpdateChecker()

                def _progress(status: str, percent: int) -> None:
                    with self._update_lock:
                        self._update_progress = {"status": status, "percent": percent, "error": None}

                staged = checker.download_and_stage(info, _progress)

                with self._update_lock:
                    self._update_progress = {"status": "swapping", "percent": 100, "error": None}

                checker.spawn_helper_and_exit(staged)

                import webview  # noqa: PLC0415
                for w in webview.windows:
                    w.destroy()

            except Exception as exc:
                try:
                    from desktop.updater import _log as _update_log  # noqa: PLC0415
                    _update_log(f"ERROR apply_update failed: {exc}")
                except Exception:
                    pass
                with self._update_lock:
                    self._update_progress = {"status": "error", "percent": 0, "error": str(exc)}

        threading.Thread(target=_run, name="desktop-apply-update", daemon=True).start()
        return self._sanitize_for_json({"started": True})

    def get_update_progress(self, params=None) -> dict:
        with self._update_lock:
            return self._sanitize_for_json(dict(self._update_progress))

    def snooze_update(self, params=None) -> dict:
        with self._update_lock:
            info = self._update_info
        if not info:
            return self._sanitize_for_json({"ok": False, "error": "no_update_info"})
        try:
            from desktop.updater import UpdateChecker  # noqa: PLC0415
            UpdateChecker().snooze(info["tag"])
            return self._sanitize_for_json({"ok": True})
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    def _get_software_update_status(self, *, force: bool = False) -> dict:
        with self._update_lock:
            cached_status = dict(self._latest_update_status or {})
            cached_info = dict(self._update_info or {})
            progress = dict(self._update_progress)
        if cached_status and not force:
            return self._sanitize_for_json({
                **cached_status,
                "progress": progress,
                "apply_supported": True,
            })
        try:
            from desktop.__version__ import __version__  # noqa: PLC0415
            from desktop.updater import UpdateChecker  # noqa: PLC0415

            checker = UpdateChecker()
            status = checker.get_latest_release_status(__version__)
            if status.get("update_available") and status.get("zip_url"):
                update_info = {
                    "version": status.get("latest_version"),
                    "tag": status.get("latest_tag"),
                    "zip_url": status.get("zip_url"),
                    "sha256_url": status.get("sha256_url"),
                }
                with self._update_lock:
                    self._update_info = update_info
            elif status.get("status") == "check_failed" and cached_info:
                status = {
                    **status,
                    "status": "available_cached",
                    "latest_version": cached_info.get("version"),
                    "latest_tag": cached_info.get("tag"),
                    "zip_url": cached_info.get("zip_url"),
                    "sha256_url": cached_info.get("sha256_url"),
                    "update_available": True,
                    "error": status.get("error"),
                }
            with self._update_lock:
                self._latest_update_status = dict(status)
                progress = dict(self._update_progress)
            return self._sanitize_for_json({
                **status,
                "progress": progress,
                "apply_supported": True,
            })
        except Exception as exc:
            return self._sanitize_for_json({
                "current_version": None,
                "latest_version": None,
                "latest_tag": None,
                "update_available": False,
                "release_url": None,
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "status": "check_failed",
                "error": f"Could not check GitHub Releases: {exc}",
                "progress": progress,
                "apply_supported": True,
            })
