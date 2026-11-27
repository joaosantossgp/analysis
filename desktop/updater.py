"""
Desktop auto-updater — checks GitHub Releases, downloads, validates, and stages updates.

Flow:
  UpdateChecker.get_latest_release_status() — background thread on startup;
    lists publications and offers the newest one the update channel accepts
  UpdateChecker.download_and_stage() — triggered by user action via bridge
  UpdateChecker.spawn_helper_and_exit() — spawns update_helper.ps1, then app exits
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import requests

GITHUB_REPO = "joaosantossgp/analysis"
_API_BASE = "https://api.github.com"
_APPDATA_DIR = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "CVMAnalytics"
_SNOOZE_FILE = _APPDATA_DIR / "snooze.json"
# The update channel is a local preference next to the snooze file: outside the
# bundle and outside the financial database, so updates and data resets keep it.
_CHANNEL_FILE = _APPDATA_DIR / "update_channel.json"
CHANNEL_RELEASES = "releases"
CHANNEL_PRERELEASES = "prereleases"
UPDATE_CHANNELS = (CHANNEL_RELEASES, CHANNEL_PRERELEASES)
_VERSIONS_DIR = _APPDATA_DIR / "versions"
_SNOOZE_DAYS = 7
_RELEASES_PER_PAGE = 100  # GitHub's maximum
_MAX_RELEASE_PAGES = 5  # bounds one check to five listing requests
_VERSION_NUMBER = r"(?:0|[1-9][0-9]*)"
# `git describe` appends this suffix only for commits after a tag, so zero is invalid.
_GIT_DESCRIBE_DISTANCE = r"(?:[1-9][0-9]*)"
_VERSION_RE = re.compile(
    rf"v?({_VERSION_NUMBER})\.({_VERSION_NUMBER})\.({_VERSION_NUMBER})"
    rf"(?:-rc\.({_VERSION_NUMBER}))?(?:-{_GIT_DESCRIBE_DISTANCE}-g[0-9a-f]+)?$"
)
# Shared with update_helper.ps1 ($LogPath) and tailed by the Status page
# (bridge._collect_recent_diagnostics). The whole install flow logs here so a
# failure remains inspectable after the app process exits.
_UPDATE_LOG = _APPDATA_DIR / "update_error.log"


def _log(message: str) -> None:
    """Best-effort append to the persistent update log. Never raises."""
    try:
        _APPDATA_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with _UPDATE_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"[{ts}] {message}\n")
    except Exception:
        pass


def _parse_version(tag: str) -> tuple[int, ...]:
    """Parse only project stable/rc.N versions and git-describe suffixes."""
    m = _VERSION_RE.fullmatch(tag.strip())
    if m:
        major, minor, patch, rc = m.groups()
        return (
            int(major),
            int(minor),
            int(patch),
            1 if rc is None else 0,
            int(rc or 0),
        )
    return (0,)


def get_update_channel() -> str:
    """The stored update channel; a missing or unreadable file means releases only."""
    try:
        channel = json.loads(_CHANNEL_FILE.read_text(encoding="utf-8")).get("channel")
    except Exception:
        return CHANNEL_RELEASES
    return channel if channel in UPDATE_CHANNELS else CHANNEL_RELEASES


def set_update_channel(channel: str) -> None:
    if channel not in UPDATE_CHANNELS:
        raise ValueError("invalid_channel")
    _APPDATA_DIR.mkdir(parents=True, exist_ok=True)
    # Swap in a complete file so a crash mid-write keeps the previous choice.
    tmp = _CHANNEL_FILE.with_name(f"{_CHANNEL_FILE.name}.tmp")
    tmp.write_text(json.dumps({"channel": channel}), encoding="utf-8")
    os.replace(tmp, _CHANNEL_FILE)


def _channel_version(publication, channel: str) -> tuple[int, ...] | None:
    """The parsed version of a publication the channel accepts, else None."""
    if not isinstance(publication, dict) or publication.get("draft"):
        return None
    version = _parse_version(str(publication.get("tag_name") or ""))
    if version == (0,):
        return None
    # A legacy -rc.N tag is a pre-release even when GitHub's flag was not set.
    if channel != CHANNEL_PRERELEASES and (publication.get("prerelease") or _is_rc(version)):
        return None
    return version


def _is_rc(version: tuple[int, ...]) -> bool:
    return version[3] == 0  # _parse_version puts 0 there for an -rc.N tag


def select_publication(
    publications: list, current_version: str, channel: str
) -> dict | None:
    """Pick the publication to show for a channel from a GitHub Releases listing.

    "releases" accepts releases only (no prerelease flag and no -rc.N tag);
    "prereleases" accepts both. Drafts and malformed tags are ignored. The
    result is the newest accepted publication that is newer than the current
    version and has its package; when no newer
    one has the package, the newest newer one (so the caller can report the
    missing asset); otherwise the newest accepted one, flagged `newer: False`.
    Download URLs are only returned for a newer publication.
    """
    local = _parse_version(current_version)
    accepted = []
    for publication in publications:
        version = _channel_version(publication, channel)
        if version is None:
            continue
        tag = str(publication.get("tag_name") or "")
        zip_url, sha256_url = UpdateChecker._find_asset_urls(
            publication.get("assets") or [], tag
        )
        accepted.append((version, tag, zip_url, sha256_url, publication))
    if not accepted:
        return None
    accepted.sort(key=lambda item: item[0], reverse=True)
    newer = [item for item in accepted if item[0] > local]
    with_package = [item for item in newer if item[2]]
    version, tag, zip_url, sha256_url, publication = (with_package or newer or accepted)[0]
    is_newer = version > local
    return {
        "tag": tag,
        "version": tag.lstrip("v"),
        "kind": "pre-release" if publication.get("prerelease") or _is_rc(version) else "release",
        "newer": is_newer,
        "release_url": publication.get("html_url") or None,
        "zip_url": zip_url if is_newer else None,
        "sha256_url": sha256_url if is_newer else None,
    }


class UpdateChecker:
    def get_latest_release_status(
        self, current_version: str, channel: str | None = None
    ) -> dict:
        """Return a non-destructive update status for the user's update channel.

        This does not download, stage, or apply anything.
        """
        channel = channel or get_update_channel()
        checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        base = {
            "current_version": current_version,
            "latest_version": None,
            "latest_tag": None,
            "update_available": False,
            "release_url": None,
            "zip_url": None,
            "sha256_url": None,
            "asset_name": None,
            "sha256_asset_name": None,
            "checked_at": checked_at,
            "status": "unknown",
            "error": None,
            "can_apply": False,
            "channel": channel,
            "publication_kind": None,
        }
        try:
            publications = self._fetch_publications(channel)
        except Exception as exc:
            return {
                **base,
                "status": "check_failed",
                "error": f"Could not check GitHub Releases: {exc}",
            }

        selected = select_publication(publications, current_version, channel)
        if not selected:
            return {
                **base,
                "status": "no_release",
                "error": "GitHub Releases lists no publication for this update channel.",
            }

        tag = selected["tag"]
        zip_url = selected["zip_url"]
        sha256_url = selected["sha256_url"]
        zip_name = f"CVMAnalytics-windows-v{selected['version']}.zip"

        status = "up_to_date"
        error = None
        if selected["newer"] and not zip_url:
            status = "asset_missing"
            error = f"Publication {tag} does not include {zip_name}."
        elif selected["newer"] and self.is_snoozed(tag):
            status = "snoozed"
        elif selected["newer"]:
            status = "available"

        return {
            **base,
            "latest_version": selected["version"],
            "latest_tag": tag,
            "update_available": status == "available",
            "release_url": selected["release_url"],
            "zip_url": zip_url,
            "sha256_url": sha256_url,
            "asset_name": zip_name if zip_url else None,
            "sha256_asset_name": f"{zip_name}.sha256" if sha256_url else None,
            "status": status,
            "error": error,
            "can_apply": status == "available",
            "publication_kind": selected["kind"],
        }

    def check_for_update(
        self, current_version: str, channel: str | None = None
    ) -> dict | None:
        """
        Return update info if the user's update channel has a newer publication
        with its package that is not snoozed. Returns None on network error or
        if already up to date.
        """
        channel = channel or get_update_channel()
        try:
            publications = self._fetch_publications(channel)
        except Exception:
            return None

        selected = select_publication(publications, current_version, channel)
        if not selected or not selected["newer"] or not selected["zip_url"]:
            return None
        if self.is_snoozed(selected["tag"]):
            return None

        return {
            "version": selected["version"],
            "tag": selected["tag"],
            "zip_url": selected["zip_url"],
            "sha256_url": selected["sha256_url"],
        }

    def is_snoozed(self, tag: str) -> bool:
        try:
            data = json.loads(_SNOOZE_FILE.read_text())
            if data.get("tag") == tag and data.get("until_ts", 0) > time.time():
                return True
        except Exception:
            pass
        return False

    def snooze(self, tag: str, days: int = _SNOOZE_DAYS) -> None:
        _APPDATA_DIR.mkdir(parents=True, exist_ok=True)
        _SNOOZE_FILE.write_text(
            json.dumps({"tag": tag, "until_ts": time.time() + days * 86400})
        )

    def download_and_stage(
        self,
        update_info: dict,
        progress_cb: Callable[[str, int], None],
    ) -> Path:
        """
        Download, validate, and extract the new bundle.
        progress_cb(status, percent) — called throughout.
        Raises on checksum mismatch or extraction failure.
        Returns the path to the extracted version directory.
        """
        version = update_info["version"]
        zip_url = update_info["zip_url"]
        sha256_url = update_info.get("sha256_url")

        zip_name = f"CVMAnalytics-windows-v{version}.zip"
        tmp_dir = Path(tempfile.gettempdir())
        zip_path = tmp_dir / zip_name
        sha256_path = tmp_dir / f"{zip_name}.sha256"

        _log(f"download_and_stage start: version={version} asset={zip_name} url={zip_url}")
        _log(f"download dest={zip_path}")
        progress_cb("downloading", 0)
        self._download_file(zip_url, zip_path, progress_cb)

        if sha256_url:
            progress_cb("validating", 90)
            try:
                self._download_file(sha256_url, sha256_path, lambda *_: None)
                self._validate_sha256(zip_path, sha256_path)
            except Exception:
                zip_path.unlink(missing_ok=True)
                sha256_path.unlink(missing_ok=True)
                raise

        progress_cb("extracting", 92)
        dest = _VERSIONS_DIR / version
        _log(f"extracting to staging dir={dest}")
        try:
            if dest.exists():
                import shutil
                shutil.rmtree(dest)
            dest.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(dest)
        except Exception as exc:
            import shutil
            shutil.rmtree(dest, ignore_errors=True)
            _log(f"ERROR extraction_failed: {exc}")
            raise RuntimeError("extraction_failed")
        finally:
            zip_path.unlink(missing_ok=True)
            sha256_path.unlink(missing_ok=True)

        staged_exe = dest / "CVMAnalytics.exe"
        staged_internal = dest / "_internal"
        _log(
            f"staged ready: dir={dest} exe_exists={staged_exe.exists()} "
            f"internal_exists={staged_internal.exists()}"
        )
        progress_cb("ready", 100)
        return dest

    def spawn_helper_and_exit(self, staged_path: Path) -> None:
        """
        Spawn the detached PowerShell helper that swaps files and relaunches,
        then signal the webview to close.
        """
        current_dir = self._current_exe_dir()
        helper = self._get_helper_path()
        target_exe = current_dir / "CVMAnalytics.exe"

        _log(
            f"spawn_helper: helper={helper} helper_exists={helper.exists()} "
            f"staged={staged_path} current_dir={current_dir} "
            f"relaunch_target={target_exe}"
        )
        if not helper.exists():
            _log("ERROR helper script not found in bundle; app will close without relaunch")
            raise RuntimeError("update_helper_missing")

        try:
            subprocess.Popen(
                [
                    "powershell.exe",
                    "-NonInteractive",
                    "-ExecutionPolicy", "Bypass",
                    "-File", str(helper),
                    str(staged_path),
                    str(current_dir),
                ],
                creationflags=(
                    subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                ),
                close_fds=True,
            )
        except Exception as exc:
            _log(f"ERROR failed to spawn update helper: {exc}")
            raise
        _log("helper spawned (detached); app exiting shortly")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_publications(channel: str) -> list:
        """List publications page by page until one the channel accepts appears.

        GitHub lists the newest publications first, so the first page holding an
        accepted publication decides the selection. At most _MAX_RELEASE_PAGES
        pages are read; beyond them the channel reads as having no publication.
        """
        publications: list = []
        for page in range(1, _MAX_RELEASE_PAGES + 1):
            resp = requests.get(
                f"{_API_BASE}/repos/{GITHUB_REPO}/releases",
                params={"per_page": _RELEASES_PER_PAGE, "page": page},
                headers={"Accept": "application/vnd.github+json"},
                timeout=10,
            )
            resp.raise_for_status()
            listed = resp.json()
            if not isinstance(listed, list):
                raise ValueError("unexpected GitHub Releases response")
            publications.extend(listed)
            if len(listed) < _RELEASES_PER_PAGE or any(
                _channel_version(item, channel) for item in listed
            ):
                break
        return publications

    @staticmethod
    def _find_asset_urls(
        assets: list[dict], tag: str
    ) -> tuple[str | None, str | None]:
        ver = tag.lstrip("v")
        zip_name = f"CVMAnalytics-windows-v{ver}.zip"
        sha256_name = f"{zip_name}.sha256"
        zip_url = sha256_url = None
        for asset in assets:
            name = asset.get("name", "")
            url = asset.get("browser_download_url", "")
            if name == zip_name:
                zip_url = url
            elif name == sha256_name:
                sha256_url = url
        return zip_url, sha256_url

    @staticmethod
    def _download_file(
        url: str,
        dest: Path,
        progress_cb: Callable[[str, int], None],
    ) -> None:
        with requests.get(url, stream=True, timeout=30) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with dest.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = min(int(downloaded / total * 85), 85)
                            progress_cb("downloading", pct)

    @staticmethod
    def _validate_sha256(zip_path: Path, sha256_path: Path) -> None:
        expected_line = sha256_path.read_text().strip().split()[0].lower()
        h = hashlib.sha256()
        with zip_path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        if h.hexdigest() != expected_line:
            raise ValueError("checksum_mismatch")

    @staticmethod
    def _get_helper_path() -> Path:
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS) / "update_helper.ps1"  # type: ignore[attr-defined]
        return Path(__file__).parent / "update_helper.ps1"

    @staticmethod
    def _current_exe_dir() -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent
        return Path(__file__).parent.parent / "dist" / "CVMAnalytics"
