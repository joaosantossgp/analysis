"""Software update bridge methods extracted from desktop/bridge_api/status.py."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger("desktop.bridge")

class StatusUpdatesMixin:
    def _updates_managed_by_git(self) -> bool:
        return self._runtime_mode() in {"vite-dev", "vite-dev-release-data"}

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
        """Last known update status. `force` runs a new check against GitHub."""
        from desktop.__version__ import __version__  # noqa: PLC0415
        from desktop.updater import get_update_channel  # noqa: PLC0415

        if self._updates_managed_by_git():
            return {"available": False, "status": "managed_by_git"}
        if self._truthy((params or {}).get("force", False)):
            self._get_software_update_status(force=True)
        with self._update_lock:
            info = self._update_info
            status = dict(self._latest_update_status or {})
        result = {
            "available": False,
            "status": status.get("status") or "not_checked",
            "error": status.get("error"),
            "channel": status.get("channel") or get_update_channel(),
            "publication_kind": status.get("publication_kind"),
            "checked_at": status.get("checked_at"),
            "current_version": status.get("current_version") or __version__,
            "latest_version": status.get("latest_version"),
            "release_url": status.get("release_url"),
        }
        if info:
            result.update(available=True, version=info["version"], zip_url=info["zip_url"])
        return self._sanitize_for_json(result)

    def get_update_channel(self, params=None) -> dict:
        from desktop.updater import get_update_channel  # noqa: PLC0415

        return self._sanitize_for_json({"channel": get_update_channel()})

    def set_update_channel(self, params=None) -> dict:
        """Store the update channel, then check GitHub once for it.

        Choosing a channel is an explicit user action, so it runs the same check
        as "Check now" and stores the result; later status reads (get_app_status,
        check_update) reuse it and never contact GitHub because of the change.
        """
        from desktop.__version__ import __version__  # noqa: PLC0415
        from desktop.updater import _log as _update_log  # noqa: PLC0415
        from desktop.updater import get_update_channel, set_update_channel  # noqa: PLC0415

        if self._updates_managed_by_git():
            return {"ok": False, "error": "managed_by_git", "channel": get_update_channel()}
        if not self._is_write_allowed():
            return self._sanitize_for_json({
                **self._write_blocked_response("set_update_channel"),
                "channel": get_update_channel(),
            })
        channel = str((params or {}).get("channel") or "")
        # One lock for the write and the reset, so a check finishing now cannot
        # store an offer for the previous channel (see _get_software_update_status).
        with self._update_lock:
            try:
                set_update_channel(channel)
            except ValueError:
                return self._sanitize_for_json({
                    "ok": False, "error": "invalid_channel", "channel": get_update_channel(),
                })
            except OSError as exc:
                return self._sanitize_for_json({
                    "ok": False, "error": str(exc), "channel": get_update_channel(),
                })
            self._update_info = None
            # Never None: an empty cache makes the next status read call GitHub.
            # Reads during the check below see the new channel as not checked yet.
            self._latest_update_status = {
                "current_version": __version__,
                "latest_version": None,
                "latest_tag": None,
                "update_available": False,
                "release_url": None,
                "checked_at": None,
                "status": "unknown",
                "error": None,
                "can_apply": False,
                "channel": channel,
                "publication_kind": None,
            }
        status = self._get_software_update_status(force=True)
        _update_log(f"update channel set to {channel}; check result: {status.get('status')}")
        return self._sanitize_for_json({"ok": True, "channel": channel})

    def apply_update(self, params=None) -> dict:
        if self._updates_managed_by_git():
            return {"error": "managed_by_git"}
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
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})
        # Status reads now answer like the next startup check will: postponed, nothing to apply.
        with self._update_lock:
            if self._update_info is info:
                self._update_info = None
                self._latest_update_status = {
                    **(self._latest_update_status or {}),
                    "status": "snoozed",
                    "update_available": False,
                    "can_apply": False,
                }
        return self._sanitize_for_json({"ok": True})

    def _get_software_update_status(self, *, force: bool = False) -> dict:
        if self._updates_managed_by_git():
            return {
                "status": "managed_by_git", "current_version": None, "latest_version": None,
                "update_available": False, "apply_supported": False, "can_apply": False,
            }
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
            from desktop.updater import UpdateChecker, get_update_channel  # noqa: PLC0415

            checker = UpdateChecker()
            status = checker.get_latest_release_status(__version__)
            update_info = None
            if status.get("update_available") and status.get("zip_url"):
                update_info = {
                    "version": status.get("latest_version"),
                    "tag": status.get("latest_tag"),
                    "zip_url": status.get("zip_url"),
                    "sha256_url": status.get("sha256_url"),
                    "publication_kind": status.get("publication_kind"),
                }
            with self._update_lock:
                stale = status.get("channel") not in (None, get_update_channel())
                if update_info and not stale:
                    self._update_info = update_info
            if stale:
                # The channel changed while GitHub answered: check the new one instead.
                return self._get_software_update_status(force=True)
            if status.get("status") == "check_failed" and cached_info:
                status = {
                    **status,
                    "status": "available_cached",
                    "latest_version": cached_info.get("version"),
                    "latest_tag": cached_info.get("tag"),
                    "publication_kind": cached_info.get("publication_kind"),
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
            status = {
                "current_version": None,
                "latest_version": None,
                "latest_tag": None,
                "update_available": False,
                "release_url": None,
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "status": "check_failed",
                "error": f"Could not check GitHub Releases: {exc}",
            }
            # Stored like any failed check, so later reads do not retry GitHub.
            with self._update_lock:
                self._latest_update_status = dict(status)
            return self._sanitize_for_json({
                **status,
                "progress": progress,
                "apply_supported": True,
            })
