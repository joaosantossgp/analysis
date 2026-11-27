"""Bridge contract for the update channel (#626, ADR 0011)."""
from __future__ import annotations

import pytest

from desktop import updater
from desktop.bridge import CVMBridge


def _publication(tag, *, prerelease=False):
    zip_name = f"CVMAnalytics-windows-v{tag.lstrip('v')}.zip"
    return {
        "tag_name": tag,
        "prerelease": prerelease,
        "draft": False,
        "html_url": f"https://example.test/releases/{tag}",
        "assets": [
            {"name": zip_name, "browser_download_url": f"https://example.test/{zip_name}"},
            {"name": f"{zip_name}.sha256", "browser_download_url": f"https://example.test/{zip_name}.sha256"},
        ],
    }


PUBLISHED = [_publication("v0.30.0-rc.1", prerelease=True), _publication("v0.29.2")]


@pytest.fixture(autouse=True)
def _installed_0_29_2(tmp_path, monkeypatch):
    """An installed 0.29.2 with its own preferences folder and normal write access."""
    appdata = tmp_path / "LocalAppData" / "CVMAnalytics"
    monkeypatch.setattr(updater, "_APPDATA_DIR", appdata)
    monkeypatch.setattr(updater, "_CHANNEL_FILE", appdata / "update_channel.json")
    monkeypatch.setattr(updater, "_SNOOZE_FILE", appdata / "snooze.json")
    monkeypatch.setattr("desktop.__version__.__version__", "0.29.2")
    monkeypatch.delenv("CVMANALYTICS_USE_RELEASE_DATA", raising=False)
    monkeypatch.delenv("CVMANALYTICS_CONCURRENT_LOCK_DETECTED", raising=False)
    return appdata


@pytest.fixture
def online(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return PUBLISHED

    monkeypatch.setattr(updater.requests, "get", lambda *args, **kwargs: Response())


@pytest.fixture
def offline(monkeypatch):
    def _get(*args, **kwargs):
        raise updater.requests.ConnectionError("no network")

    monkeypatch.setattr(updater.requests, "get", _get)


def test_channel_defaults_to_releases_only():
    assert CVMBridge().get_update_channel() == {"channel": "releases"}


def test_channel_is_stored_outside_the_bundle_and_survives_a_new_app_process(_installed_0_29_2):
    result = CVMBridge().set_update_channel({"channel": "prereleases"})

    assert result == {"ok": True, "channel": "prereleases"}
    # A fresh bridge is what the updated app starts with: only the file carries the choice.
    assert CVMBridge().get_update_channel() == {"channel": "prereleases"}
    assert (_installed_0_29_2 / "update_channel.json").is_file()


def test_unknown_channel_is_refused_and_the_choice_is_kept():
    bridge = CVMBridge()
    bridge.set_update_channel({"channel": "prereleases"})

    result = bridge.set_update_channel({"channel": "nightly"})

    assert result["ok"] is False
    assert result["error"] == "invalid_channel"
    assert result["channel"] == "prereleases"
    assert bridge.get_update_channel() == {"channel": "prereleases"}


def test_read_only_mode_refuses_to_change_the_channel(monkeypatch, _installed_0_29_2):
    monkeypatch.setenv("CVMANALYTICS_USE_RELEASE_DATA", "1")
    monkeypatch.delenv("CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES", raising=False)
    bridge = CVMBridge()

    result = bridge.set_update_channel({"channel": "prereleases"})

    assert result["ok"] is False
    assert result["status_reason_code"] == "release_data_write_blocked"
    assert bridge.get_update_channel() == {"channel": "releases"}
    assert not (_installed_0_29_2 / "update_channel.json").exists()


def test_update_status_reports_channel_publication_kind_and_last_check(online):
    bridge = CVMBridge()
    bridge.set_update_channel({"channel": "prereleases"})

    status = bridge._get_software_update_status(force=True)

    assert status["status"] == "available"
    assert status["channel"] == "prereleases"
    assert status["publication_kind"] == "pre-release"
    assert status["latest_version"] == "0.30.0-rc.1"
    assert status["checked_at"]


def test_check_update_keeps_its_fields_and_adds_the_channel_view(online):
    bridge = CVMBridge()
    bridge.set_update_channel({"channel": "prereleases"})

    result = bridge.check_update({"force": True})

    assert result["available"] is True
    assert result["version"] == "0.30.0-rc.1"
    assert result["zip_url"] == "https://example.test/CVMAnalytics-windows-v0.30.0-rc.1.zip"
    assert result["status"] == "available"
    assert result["channel"] == "prereleases"
    assert result["publication_kind"] == "pre-release"
    assert result["current_version"] == "0.29.2"
    assert result["latest_version"] == "0.30.0-rc.1"
    assert result["checked_at"]


def test_check_update_before_any_check_reports_channel_without_a_network_call(offline):
    result = CVMBridge().check_update()

    assert result["available"] is False
    assert result["status"] == "not_checked"
    assert result["channel"] == "releases"
    assert result["current_version"] == "0.29.2"
    assert result["checked_at"] is None


def test_releases_only_is_up_to_date_on_the_newest_release(online):
    result = CVMBridge().check_update({"force": True})

    assert result["available"] is False
    assert result["status"] == "up_to_date"
    assert result["channel"] == "releases"
    assert result["publication_kind"] == "release"
    assert result["latest_version"] == "0.29.2"


def test_switching_back_to_releases_only_drops_the_offered_pre_release(online):
    bridge = CVMBridge()
    bridge.set_update_channel({"channel": "prereleases"})
    assert bridge.check_update({"force": True})["available"] is True

    bridge.set_update_channel({"channel": "releases"})

    # Nothing is offered or installable until the new channel has been checked.
    assert bridge.check_update()["available"] is False
    assert bridge.apply_update() == {"error": "no_update_available"}
    assert bridge.check_update({"force": True})["status"] == "up_to_date"


def test_switching_back_while_offline_never_reuses_the_cached_pre_release(online, monkeypatch):
    bridge = CVMBridge()
    bridge.set_update_channel({"channel": "prereleases"})
    assert bridge.check_update({"force": True})["available"] is True

    def _get(*args, **kwargs):
        raise updater.requests.ConnectionError("no network")

    monkeypatch.setattr(updater.requests, "get", _get)
    bridge.set_update_channel({"channel": "releases"})
    result = bridge.check_update({"force": True})

    assert result["available"] is False
    assert result["status"] == "check_failed"
    assert result["channel"] == "releases"
    assert "Could not check GitHub Releases" in result["error"]


def test_check_that_finishes_after_a_channel_switch_does_not_offer_the_old_channel(monkeypatch):
    bridge = CVMBridge()
    bridge.set_update_channel({"channel": "prereleases"})

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return PUBLISHED

    def _get(*args, **kwargs):
        # The user switches back while GitHub is still answering the startup check.
        if updater.get_update_channel() == "prereleases":
            bridge.set_update_channel({"channel": "releases"})
        return Response()

    monkeypatch.setattr(updater.requests, "get", _get)
    status = bridge._get_software_update_status(force=True)

    assert status["channel"] == "releases"
    assert status["status"] == "up_to_date"
    assert bridge.check_update()["available"] is False


def test_offline_check_on_the_same_channel_keeps_the_cached_offer(online, monkeypatch):
    bridge = CVMBridge()
    bridge.set_update_channel({"channel": "prereleases"})
    bridge.check_update({"force": True})

    def _get(*args, **kwargs):
        raise updater.requests.ConnectionError("no network")

    monkeypatch.setattr(updater.requests, "get", _get)
    status = bridge._get_software_update_status(force=True)

    assert status["status"] == "available_cached"
    assert status["channel"] == "prereleases"
    assert status["publication_kind"] == "pre-release"
    assert status["latest_version"] == "0.30.0-rc.1"
