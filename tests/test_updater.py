from pathlib import Path

import pytest

from desktop import updater


@pytest.fixture(autouse=True)
def _isolated_appdata(tmp_path, monkeypatch):
    """Never read or write the real %LOCALAPPDATA%\\CVMAnalytics preferences."""
    monkeypatch.setattr(updater, "_APPDATA_DIR", tmp_path)
    monkeypatch.setattr(updater, "_CHANNEL_FILE", tmp_path / "update_channel.json")
    monkeypatch.setattr(updater, "_SNOOZE_FILE", tmp_path / "snooze.json")


def _publication(tag, *, prerelease=False, asset=True, draft=False):
    version = tag.lstrip("v")
    zip_name = f"CVMAnalytics-windows-v{version}.zip"
    assets = [
        {"name": zip_name, "browser_download_url": f"https://example.test/{zip_name}"},
        {
            "name": f"{zip_name}.sha256",
            "browser_download_url": f"https://example.test/{zip_name}.sha256",
        },
        # Unversioned copies exist on every published release and are never the package.
        {"name": "CVMAnalytics-windows.zip", "browser_download_url": "https://example.test/latest.zip"},
    ]
    return {
        "tag_name": tag,
        "prerelease": prerelease,
        "draft": draft,
        "html_url": f"https://example.test/releases/{tag}",
        "assets": assets if asset else assets[2:],
    }


def _serve(monkeypatch, publications):
    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return publications

    def _get(url, *args, **kwargs):
        calls.append(url)
        return Response()

    monkeypatch.setattr(updater.requests, "get", _get)
    return calls


def _serve_pages(monkeypatch, pages):
    """Serve GitHub's paginated listing: `pages[n - 1]` for `?page=n`, then empty pages."""
    requested = []

    class Response:
        def __init__(self, body):
            self.body = body

        def raise_for_status(self):
            return None

        def json(self):
            return self.body

    def _get(url, *args, params=None, **kwargs):
        page = params["page"]
        requested.append(page)
        return Response(pages[page - 1] if page <= len(pages) else [])

    monkeypatch.setattr(updater.requests, "get", _get)
    return requested


def _offline(monkeypatch):
    def _get(*args, **kwargs):
        raise updater.requests.ConnectionError("no network")

    monkeypatch.setattr(updater.requests, "get", _get)


# What GitHub lists today: one legacy pre-release above the last release.
PUBLISHED = [
    _publication("v0.30.0-rc.1", prerelease=True),
    _publication("v0.29.2"),
    _publication("v0.29.1"),
]
# The same list after plain-number publications start (ADR 0011); 0.30.1 was promoted.
PLAIN = [
    _publication("v0.30.2", prerelease=True),
    _publication("v0.30.1"),
    _publication("v0.30.0"),
    *PUBLISHED,
]
MALFORMED = [
    _publication("v0.31.0-rc.foo"),
    _publication("v01.31.0"),
    _publication("v0.31.0-0-gdeadbeef"),
    _publication("nightly", prerelease=True),
    {"tag_name": None, "assets": []},
    "not a publication",
]


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


# (publications, installed version, channel) -> tag offered as an update, or None.
SELECTION_CASES = [
    # Channel filtering against what is published today.
    pytest.param(PUBLISHED, "0.29.2", "releases", None, id="releases-only-ignores-pre-release"),
    pytest.param(PUBLISHED, "0.29.2", "prereleases", "v0.30.0-rc.1", id="pre-release-channel-gets-pre-release"),
    pytest.param(PUBLISHED, "0.29.1", "releases", "v0.29.2", id="releases-only-gets-newest-release"),
    pytest.param(PUBLISHED, "0.29.1", "prereleases", "v0.30.0-rc.1", id="pre-release-channel-gets-newest-of-both"),
    pytest.param(PUBLISHED, "0.30.0-rc.1", "prereleases", None, id="already-on-newest"),
    # No downgrade after switching back to "releases only".
    pytest.param(PUBLISHED, "0.30.0-rc.1", "releases", None, id="no-downgrade-from-rc-to-older-release"),
    pytest.param(PLAIN, "0.30.2", "releases", None, id="no-downgrade-from-plain-pre-release"),
    # -rc.N and plain versions mixed.
    pytest.param(PLAIN, "0.29.2", "releases", "v0.30.1", id="old-release-install-gets-plain-release"),
    pytest.param(PLAIN, "0.29.2", "prereleases", "v0.30.2", id="old-release-install-gets-plain-pre-release"),
    pytest.param(PLAIN, "0.30.0-rc.1", "releases", "v0.30.1", id="rc-install-gets-plain-release"),
    pytest.param(PLAIN, "0.30.0-rc.1", "prereleases", "v0.30.2", id="rc-install-gets-plain-pre-release"),
    pytest.param(PLAIN, "0.30.1", "prereleases", "v0.30.2", id="release-install-on-pre-release-channel"),
    pytest.param(PLAIN, "0.30.1", "releases", None, id="release-install-up-to-date"),
    pytest.param(PLAIN, "v0.30.1-4-gad7eaf", "releases", None, id="git-describe-build-of-newest-release"),
    # Versions compare as numbers and the listing order does not matter.
    pytest.param(
        [_publication("v0.9.0"), _publication("v0.30.0"), _publication("v0.10.0")],
        "0.8.0", "releases", "v0.30.0", id="numeric-not-alphabetical",
    ),
    pytest.param(list(reversed(PLAIN)), "0.29.2", "prereleases", "v0.30.2", id="unsorted-listing"),
    # Malformed tags are never offered.
    pytest.param(MALFORMED + PUBLISHED, "0.29.1", "prereleases", "v0.30.0-rc.1", id="malformed-ignored-next-to-valid"),
    pytest.param(MALFORMED, "0.29.1", "prereleases", None, id="only-malformed"),
    pytest.param([], "0.29.1", "prereleases", None, id="nothing-published"),
    pytest.param(
        [_publication("v0.31.0", draft=True), *PUBLISHED], "0.29.2", "releases", None, id="draft-ignored",
    ),
    # A legacy -rc.N tag published without GitHub's prerelease flag is still a pre-release.
    pytest.param(
        [_publication("v0.30.0-rc.2"), *PUBLISHED], "0.29.2", "releases", None,
        id="releases-only-ignores-unflagged-rc-tag",
    ),
    pytest.param(
        [_publication("v0.30.0-rc.2"), *PUBLISHED], "0.29.2", "prereleases", "v0.30.0-rc.2",
        id="pre-release-channel-gets-unflagged-rc-tag",
    ),
    # Missing package: fall back to the newest publication that has one.
    pytest.param(
        [_publication("v0.30.2", asset=False), *PLAIN[1:]], "0.30.0", "releases", "v0.30.1",
        id="missing-asset-falls-back-to-older-newer-publication",
    ),
    pytest.param(
        [_publication("v0.30.2", asset=False), *PLAIN[1:]], "0.30.1", "releases", None,
        id="missing-asset-and-nothing-else-newer",
    ),
    # Retention (#634) removes the files of pre-releases older than the newest 10: never offered.
    pytest.param(
        [_publication("v0.30.12", prerelease=True), _publication("v0.30.1", prerelease=True, asset=False)],
        "0.30.0", "prereleases", "v0.30.12", id="pruned-pre-release-never-offered",
    ),
]


def _offered_tag(selected):
    if selected and selected["newer"] and selected["zip_url"]:
        return selected["tag"]
    return None


@pytest.mark.parametrize(("publications", "current", "channel", "expected"), SELECTION_CASES)
def test_select_publication_offers_newest_acceptable_for_channel(
    publications, current, channel, expected
):
    assert _offered_tag(updater.select_publication(publications, current, channel)) == expected


@pytest.mark.parametrize(("publications", "current", "channel", "expected"), SELECTION_CASES)
def test_both_updater_paths_offer_the_selected_publication(
    monkeypatch, publications, current, channel, expected
):
    _serve(monkeypatch, publications)
    checker = updater.UpdateChecker()

    status = checker.get_latest_release_status(current, channel)
    update = checker.check_for_update(current, channel)

    assert status["update_available"] is (expected is not None)
    assert status["can_apply"] is (expected is not None)
    assert (status["latest_tag"] if status["update_available"] else None) == expected
    assert (update or {}).get("tag") == expected


def test_selected_publication_carries_kind_and_versioned_package():
    selected = updater.select_publication(PUBLISHED, "0.29.2", "prereleases")

    assert selected == {
        "tag": "v0.30.0-rc.1",
        "version": "0.30.0-rc.1",
        "kind": "pre-release",
        "newer": True,
        "release_url": "https://example.test/releases/v0.30.0-rc.1",
        "zip_url": "https://example.test/CVMAnalytics-windows-v0.30.0-rc.1.zip",
        "sha256_url": "https://example.test/CVMAnalytics-windows-v0.30.0-rc.1.zip.sha256",
    }


def test_unflagged_rc_tag_is_labelled_pre_release():
    selected = updater.select_publication([_publication("v0.30.0-rc.2")], "0.29.2", "prereleases")

    assert selected["kind"] == "pre-release"


# A full first page of pre-releases (some legacy -rc.N tags without the flag) above the releases.
PAGE_OF_PRE_RELEASES = [_publication(f"v0.31.0-rc.{n}", prerelease=n % 2 == 0) for n in range(1, 101)]


def test_listing_reads_the_next_page_when_the_first_has_no_release_for_the_channel(monkeypatch):
    requested = _serve_pages(monkeypatch, [PAGE_OF_PRE_RELEASES, [_publication("v0.30.1"), _publication("v0.30.0")]])

    status = updater.UpdateChecker().get_latest_release_status("0.30.0", "releases")

    assert requested == [1, 2]
    assert status["status"] == "available"
    assert status["latest_tag"] == "v0.30.1"
    assert status["publication_kind"] == "release"


def test_listing_stops_at_the_first_page_that_decides_the_channel(monkeypatch):
    requested = _serve_pages(monkeypatch, [PAGE_OF_PRE_RELEASES, [_publication("v0.30.1")]])

    status = updater.UpdateChecker().get_latest_release_status("0.30.0", "prereleases")

    assert requested == [1]
    assert status["latest_tag"] == "v0.31.0-rc.100"


def test_listing_reads_at_most_five_pages(monkeypatch):
    requested = _serve_pages(monkeypatch, [PAGE_OF_PRE_RELEASES] * 6 + [[_publication("v0.30.1")]])

    status = updater.UpdateChecker().get_latest_release_status("0.30.0", "releases")

    assert requested == [1, 2, 3, 4, 5]
    assert status["status"] == "no_release"


def test_status_lists_publications_instead_of_reading_latest(monkeypatch):
    calls = _serve(monkeypatch, PUBLISHED)

    updater.UpdateChecker().get_latest_release_status("0.29.2", "prereleases")

    assert len(calls) == 1
    # Literal slug: installed apps keep the repository name they were built with (#658).
    assert calls[0] == "https://api.github.com/repos/joaosantossgp/analysis/releases"


def test_status_reports_channel_kind_and_last_check(monkeypatch):
    _serve(monkeypatch, PUBLISHED)

    status = updater.UpdateChecker().get_latest_release_status("0.29.2", "prereleases")

    assert status["status"] == "available"
    assert status["channel"] == "prereleases"
    assert status["publication_kind"] == "pre-release"
    assert status["latest_version"] == "0.30.0-rc.1"
    assert status["asset_name"] == "CVMAnalytics-windows-v0.30.0-rc.1.zip"
    assert status["sha256_asset_name"] == "CVMAnalytics-windows-v0.30.0-rc.1.zip.sha256"
    assert status["checked_at"]


def test_status_up_to_date_names_the_newest_release_of_the_channel(monkeypatch):
    _serve(monkeypatch, PUBLISHED)

    status = updater.UpdateChecker().get_latest_release_status("0.30.0-rc.1", "releases")

    assert status["status"] == "up_to_date"
    assert status["latest_version"] == "0.29.2"
    assert status["publication_kind"] == "release"
    assert status["zip_url"] is None  # nothing to apply: an older release is never a download


def test_status_uses_the_stored_channel_by_default(monkeypatch):
    _serve(monkeypatch, PUBLISHED)
    checker = updater.UpdateChecker()

    assert checker.get_latest_release_status("0.29.2")["channel"] == "releases"
    assert checker.check_for_update("0.29.2") is None

    updater.set_update_channel("prereleases")

    assert checker.get_latest_release_status("0.29.2")["latest_tag"] == "v0.30.0-rc.1"
    assert checker.check_for_update("0.29.2") == {
        "version": "0.30.0-rc.1",
        "tag": "v0.30.0-rc.1",
        "zip_url": "https://example.test/CVMAnalytics-windows-v0.30.0-rc.1.zip",
        "sha256_url": "https://example.test/CVMAnalytics-windows-v0.30.0-rc.1.zip.sha256",
    }


def test_status_reports_missing_asset_when_no_newer_publication_has_the_package(monkeypatch):
    _serve(monkeypatch, [_publication("v0.30.2", asset=False), *PLAIN[1:]])

    status = updater.UpdateChecker().get_latest_release_status("0.30.1", "releases")

    assert status["status"] == "asset_missing"
    assert status["latest_tag"] == "v0.30.2"
    assert "CVMAnalytics-windows-v0.30.2.zip" in status["error"]
    assert status["update_available"] is False
    assert status["can_apply"] is False


def test_status_reports_no_publication_when_nothing_valid_is_listed(monkeypatch):
    _serve(monkeypatch, MALFORMED)

    status = updater.UpdateChecker().get_latest_release_status("0.29.1", "prereleases")

    assert status["status"] == "no_release"
    assert status["latest_version"] is None
    assert status["update_available"] is False


def test_offline_check_fails_visibly_and_keeps_the_channel(monkeypatch):
    _offline(monkeypatch)
    checker = updater.UpdateChecker()

    status = checker.get_latest_release_status("0.29.2", "prereleases")

    assert status["status"] == "check_failed"
    assert "Could not check GitHub Releases" in status["error"]
    assert status["channel"] == "prereleases"
    assert status["update_available"] is False
    assert status["checked_at"]
    assert checker.check_for_update("0.29.2", "prereleases") is None


def test_unexpected_listing_payload_is_a_failed_check(monkeypatch):
    _serve(monkeypatch, {"message": "API rate limit exceeded"})

    status = updater.UpdateChecker().get_latest_release_status("0.29.2", "releases")

    assert status["status"] == "check_failed"
    assert updater.UpdateChecker().check_for_update("0.29.2", "releases") is None


def test_snoozed_publication_is_not_offered(monkeypatch):
    _serve(monkeypatch, PUBLISHED)
    checker = updater.UpdateChecker()
    checker.snooze("v0.29.2")

    status = checker.get_latest_release_status("0.29.1", "releases")

    assert status["status"] == "snoozed"
    assert status["update_available"] is False
    assert checker.check_for_update("0.29.1", "releases") is None


def test_update_channel_defaults_to_releases_only():
    assert updater.get_update_channel() == "releases"


def test_update_channel_round_trips_through_its_own_file(tmp_path):
    updater.set_update_channel("prereleases")

    assert updater.get_update_channel() == "prereleases"
    assert (tmp_path / "update_channel.json").is_file()

    updater.set_update_channel("releases")

    assert updater.get_update_channel() == "releases"


@pytest.mark.parametrize("content", ["", "not json", "[]", '{"channel": "nightly"}', '{"channel": 1}'])
def test_unreadable_update_channel_file_means_releases_only(tmp_path, content):
    (tmp_path / "update_channel.json").write_text(content, encoding="utf-8")

    assert updater.get_update_channel() == "releases"


def test_failed_channel_write_keeps_the_previous_choice(monkeypatch):
    updater.set_update_channel("prereleases")
    write_text = Path.write_text

    def _crash_mid_write(self, data, *args, **kwargs):
        write_text(self, data[:3], *args, **kwargs)
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", _crash_mid_write)
    with pytest.raises(OSError):
        updater.set_update_channel("releases")

    assert updater.get_update_channel() == "prereleases"


def test_unknown_update_channel_is_rejected_and_not_stored(tmp_path):
    with pytest.raises(ValueError):
        updater.set_update_channel("nightly")

    assert not (tmp_path / "update_channel.json").exists()


def test_update_helper_starts_without_a_console_and_outlives_the_app(monkeypatch, tmp_path):
    # #671: powershell.exe started with DETACHED_PROCESS exits without running the
    # helper on Windows 11 25H2, so the app closed and nothing was updated.
    flags = {"DETACHED_PROCESS": 0x8, "CREATE_NEW_PROCESS_GROUP": 0x200, "CREATE_NO_WINDOW": 0x08000000}
    for name, value in flags.items():
        monkeypatch.setattr(updater.subprocess, name, value, raising=False)  # Windows-only constants
    helper = tmp_path / "update_helper.ps1"
    helper.write_text("", encoding="utf-8")
    monkeypatch.setattr(updater.UpdateChecker, "_get_helper_path", staticmethod(lambda: helper))
    monkeypatch.setattr(updater.UpdateChecker, "_current_exe_dir", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(updater, "_log", lambda message: None)
    calls = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda args, **kwargs: calls.append((args, kwargs)))

    updater.UpdateChecker().spawn_helper_and_exit(tmp_path / "staged")

    (args, kwargs), = calls
    assert args[:2] == ["powershell.exe", "-NonInteractive"] and str(helper) in args
    assert kwargs["creationflags"] == flags["CREATE_NO_WINDOW"] | flags["CREATE_NEW_PROCESS_GROUP"]
