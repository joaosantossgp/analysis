import pytest

from desktop import updater


def test_parse_version_orders_release_candidate_before_stable_release():
    assert updater._parse_version("0.30.0-rc.1") < updater._parse_version("0.30.0")


def test_parse_version_orders_release_candidates_numerically():
    assert updater._parse_version("0.30.0-rc.1") < updater._parse_version("0.30.0-rc.2")


def test_parse_version_keeps_release_candidate_git_describe_suffix():
    assert updater._parse_version("v0.30.0-rc.1-4-gad7eaf") == updater._parse_version(
        "0.30.0-rc.1"
    )


@pytest.mark.parametrize(
    "tag",
    [
        "v0.30.0-rc.foo",
        "v0.30.0-rc.",
        "v0.30.0-rc.1-extra",
        "v0.30.0-rc.01",
        "v0.30.0-rc.01-4-gad7eaf",
        "v01.30.0-rc.1",
        "v0.30.0-0-gdeadbeef",
    ],
)
def test_parse_version_rejects_malformed_tag(tag):
    assert updater._parse_version(tag) == (0,)


def test_parse_version_keeps_git_describe_suffix_out_of_release_ordering():
    assert updater._parse_version("v0.30.0-4-gad7eaf") == updater._parse_version("0.30.0")


def test_latest_release_status_offers_stable_release_to_release_candidate(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "tag_name": "v0.30.0",
                "assets": [
                    {
                        "name": "CVMAnalytics-windows-v0.30.0.zip",
                        "browser_download_url": "https://example.test/v0.30.0.zip",
                    },
                    {
                        "name": "CVMAnalytics-windows-v0.30.0.zip.sha256",
                        "browser_download_url": "https://example.test/v0.30.0.zip.sha256",
                    },
                ],
            }

    monkeypatch.setattr(updater.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(updater.UpdateChecker, "is_snoozed", lambda self, tag: False)

    status = updater.UpdateChecker().get_latest_release_status("0.30.0-rc.1")

    assert status["status"] == "available"
    assert status["update_available"] is True
    assert status["can_apply"] is True


def test_check_for_update_offers_stable_release_to_release_candidate(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "tag_name": "v0.30.0",
                "assets": [
                    {
                        "name": "CVMAnalytics-windows-v0.30.0.zip",
                        "browser_download_url": "https://example.test/v0.30.0.zip",
                    },
                    {
                        "name": "CVMAnalytics-windows-v0.30.0.zip.sha256",
                        "browser_download_url": "https://example.test/v0.30.0.zip.sha256",
                    },
                ],
            }

    monkeypatch.setattr(updater.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(updater.UpdateChecker, "is_snoozed", lambda self, tag: False)

    update = updater.UpdateChecker().check_for_update("0.30.0-rc.1")

    assert update == {
        "version": "0.30.0",
        "tag": "v0.30.0",
        "zip_url": "https://example.test/v0.30.0.zip",
        "sha256_url": "https://example.test/v0.30.0.zip.sha256",
    }


def test_latest_release_status_does_not_offer_release_candidate_to_stable(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "tag_name": "v0.30.0-rc.2",
                "assets": [
                    {
                        "name": "CVMAnalytics-windows-v0.30.0-rc.2.zip",
                        "browser_download_url": "https://example.test/v0.30.0-rc.2.zip",
                    },
                ],
            }

    monkeypatch.setattr(updater.requests, "get", lambda *args, **kwargs: Response())

    status = updater.UpdateChecker().get_latest_release_status("0.30.0")

    assert status["status"] == "up_to_date"
    assert status["update_available"] is False
    assert status["can_apply"] is False


@pytest.mark.parametrize(
    ("tag", "current_version"),
    [
        ("v0.30.0-rc.foo", "0.30.0-rc.1"),
        ("v0.30.0-rc.01", "0.30.0-rc.0"),
        ("v0.30.0-rc.01-4-gad7eaf", "0.30.0-rc.0"),
        ("v0.30.0-0-gdeadbeef", "0.30.0-rc.1"),
    ],
)
def test_latest_release_status_does_not_offer_malformed_tag(
    monkeypatch, tag, current_version
):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "tag_name": tag,
                "assets": [
                    {
                        "name": f"CVMAnalytics-windows-v{tag.lstrip('v')}.zip",
                        "browser_download_url": f"https://example.test/{tag}.zip",
                    },
                ],
            }

    monkeypatch.setattr(updater.requests, "get", lambda *args, **kwargs: Response())

    status = updater.UpdateChecker().get_latest_release_status(current_version)

    assert status["status"] == "up_to_date"
    assert status["update_available"] is False
    assert status["can_apply"] is False


@pytest.mark.parametrize(
    ("tag", "current_version"),
    [
        ("v0.30.0-rc.foo", "0.30.0-rc.1"),
        ("v0.30.0-rc.01", "0.30.0-rc.0"),
        ("v0.30.0-rc.01-4-gad7eaf", "0.30.0-rc.0"),
        ("v0.30.0-0-gdeadbeef", "0.30.0-rc.1"),
    ],
)
def test_check_for_update_does_not_offer_malformed_tag(
    monkeypatch, tag, current_version
):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "tag_name": tag,
                "assets": [
                    {
                        "name": f"CVMAnalytics-windows-v{tag.lstrip('v')}.zip",
                        "browser_download_url": f"https://example.test/{tag}.zip",
                    },
                ],
            }

    monkeypatch.setattr(updater.requests, "get", lambda *args, **kwargs: Response())

    assert updater.UpdateChecker().check_for_update(current_version) is None
