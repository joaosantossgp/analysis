from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.release import promotion_workflow as w

pd, pw = w.pd, w.pw  # the module objects promotion_workflow itself uses, so monkeypatching reaches it
TODAY = "2026-11-27"


def _release(tag: str, published_at: str = "2026-10-20T12:00:00Z", *, prerelease: bool = True, draft: bool = False, body: str = "") -> dict:
    return {"id": 1, "tag_name": tag, "draft": draft, "prerelease": prerelease, "published_at": published_at,
            "html_url": f"https://github.com/o/r/releases/tag/{tag}", "body": body}  # fmt: skip


def _notes(version: str, prs: list[tuple[int, str]]) -> str:
    """Notes exactly as the publication workflow writes them."""
    facts = {"candidate_sha": "a" * 40, "last_publication": "v0.29.2"}
    decision = {"kind": "pre-release", "version": version,
                "reasons": {"prs": [{"number": n, "class": "pre", "title": t} for n, t in prs]}}  # fmt: skip
    return pw.render_notes(facts, decision)


# --- Facts for the promotion pick -----------------------------------------------

def test_publications_map_releases_for_the_pick_with_the_prs_of_their_notes() -> None:
    releases = [
        _release("v0.30.2", "2026-11-10T08:00:00Z", body=_notes("0.30.2", [(650, "Channel setting"), (651, "Fix: pill")])),
        _release("v0.30.3", draft=True),
        _release("nightly"),
        _release("v0.29.2", "2026-07-09T13:21:01Z", prerelease=False, body="Legacy notes"),
    ]
    assert w.publications(releases) == [
        {"version": "v0.30.2", "kind": "pre-release", "published_at": "2026-11-10T08:00:00Z",
         "prs": [{"number": 650, "title": "Channel setting"}, {"number": 651, "title": "Fix: pill"}]},
        {"version": "v0.29.2", "kind": "release", "published_at": "2026-07-09T13:21:01Z", "prs": []},
    ]  # fmt: skip
    assert w.latest_release(releases) == "v0.29.2"
    assert w.latest_release([_release("v0.30.1")]) is None


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("### Version\n\n0.30.2\n\n### Evidence", "0.30.2"),
        ("Steps...\nVersion: v0.30.1 (packaged)", "v0.30.1"),
        ("version v0.30.0-rc.1", "v0.30.0-rc.1"),
        ("Version: unknown", None),
        ("Versioning broke the 2.0 export", None),
        ("packaged app, version 0.30.2", None),  # only a field at the start of a line counts
        (None, None),
    ],
)
def test_found_in_reads_a_version_field_from_the_bug_body(body: str | None, expected: str | None) -> None:
    assert w.found_in(body) == expected


PUBLISHED = {"v0.30.1", "v0.30.2", "v0.30.3"}


@pytest.mark.parametrize(
    ("issue", "commit", "tags", "expected"),
    [
        # Open: blocks every pre-release, whatever the body says.
        ({"number": 1, "state": "open", "body": "Version: 0.30.2"}, None, [], {"number": 1, "found_in": None, "fixed_in": None}),
        # Closed by a PR: fixed in the earliest published tag containing its merge commit.
        ({"number": 2, "state": "closed", "state_reason": "completed", "body": "### Version\n\n0.30.1"}, "c" * 40,
         ["v0.30.3", "v0.30.2", "v0.31.0-unpublished"], {"number": 2, "found_in": "0.30.1", "fixed_in": "v0.30.2"}),
        # Fix merged but in no publication yet: still blocks.
        ({"number": 3, "state": "closed", "state_reason": "completed", "body": ""}, "c" * 40, [],
         {"number": 3, "found_in": None, "fixed_in": None}),
        # Closed by hand, or as not planned: blocks nothing.
        ({"number": 4, "state": "closed", "state_reason": "completed", "body": ""}, None, [], None),
        ({"number": 5, "state": "closed", "state_reason": "not_planned", "body": ""}, "c" * 40, ["v0.30.2"], None),
    ],
)  # fmt: skip
def test_blocking_bug_mapping(issue: dict, commit: str | None, tags: list[str], expected: dict | None) -> None:
    assert w.blocking_bug(issue, commit, tags, PUBLISHED) == expected


def test_facts_from_gh_feed_the_promotion_pick(monkeypatch: pytest.MonkeyPatch) -> None:
    releases = [
        _release("v0.30.3", "2026-11-20T00:00:00Z", body=_notes("0.30.3", [(662, "Later fix")])),
        _release("v0.30.2", "2026-11-15T00:00:00Z", body=_notes("0.30.2", [(655, "Fixes #700")])),
        _release("v0.30.1", "2026-10-20T00:00:00Z", body=_notes("0.30.1", [(650, "Channel setting")])),
        _release("v0.30.0-rc.1", "2026-07-16T01:49:48Z"),
        _release("v0.29.2", "2026-07-09T13:21:01Z", prerelease=False),
    ]
    issues = [
        {"number": 700, "state": "closed", "state_reason": "completed", "body": "Version: 0.30.1"},
        {"number": 701, "state": "closed", "state_reason": "not_planned", "body": ""},
    ]

    def fake_gh_api(path: str, jq: str, paginate: bool = True) -> list:
        if path.startswith("repos/o/r/releases"):
            return releases
        assert path == "repos/o/r/issues?state=all&labels=bug,priority:p0&per_page=100"
        assert "select(.pull_request == null)" in jq
        return issues

    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setattr(pw, "_gh_api", fake_gh_api)
    monkeypatch.setattr(w, "_closing_commit", lambda repo, number: {700: "f" * 40}.get(number))
    monkeypatch.setattr(w, "_tags_containing", lambda commit: ["v0.30.2", "v0.30.3"])
    monkeypatch.setattr(w, "_today", lambda: TODAY)

    facts = w.collect_facts()

    assert facts["blocking_bugs"] == [{"number": 700, "found_in": "0.30.1", "fixed_in": "v0.30.2"}]
    assert facts["latest_release"] == "v0.29.2"
    pick = pd.pick_promotion(facts["publications"], facts["blocking_bugs"], facts["today"])
    # The time rule picks v0.30.1 (38 days; v0.30.2 is 12 days), but bug 700 is fixed in v0.30.2.
    assert (pick["propose"], pick["version"], pick["reason"]) == (True, "0.30.2", "blocking-bug-fixed-in-newer-pre-release")
    assert pick["blocked"] == [{"version": "0.30.1", "age_days": 38, "blocking_bugs": [700]}]


# --- Proposal issue ---------------------------------------------------------------

def _facts() -> dict:
    return {
        "repository": "o/r",
        "today": TODAY,
        "latest_release": "v0.29.2",
        "publications": w.publications([
            _release("v0.30.3", "2026-11-20T00:00:00Z", body=_notes("0.30.3", [(662, "Later fix")])),
            _release("v0.30.2", "2026-11-15T00:00:00Z", body=_notes("0.30.2", [(655, "Bug fix")])),
            _release("v0.30.1", "2026-10-20T00:00:00Z", body=_notes("0.30.1", [(650, "Channel setting")])),
            _release("v0.29.2", "2026-07-09T13:21:01Z", prerelease=False, body=_notes("0.29.2", [(500, "Old")])),
        ]),
        "blocking_bugs": [],
    }  # fmt: skip


def _pick(facts: dict, bugs: list | None = None) -> dict:
    return pd.pick_promotion(facts["publications"], bugs or [], facts["today"])


def test_proposal_names_the_version_its_age_the_oldest_pre_release_and_its_prs() -> None:
    facts = _facts()
    pick = _pick(facts, [{"number": 700, "found_in": None, "fixed_in": "v0.30.2"}])
    body = w.render_proposal(facts, pick, "https://github.com/o/r/actions/runs/9")

    assert "**v0.30.2**" in body and "a pre-release for 12 days" in body
    assert "Oldest unpromoted pre-release: v0.30.1 (38 days old)" in body
    assert "Passed over: v0.30.1 (38 days old), blocking bug #700" in body
    assert "Latest release now: v0.29.2" in body
    # It carries v0.30.1 and v0.30.2, not the younger v0.30.3 nor the release before.
    assert "- #655 Bug fix" in body and "- #650 Channel setting" in body
    assert "#662" not in body and "#500" not in body
    assert body.index("v0.30.2](") < body.index("v0.30.1](")
    assert "Promote Release" in body and "`0.30.2`" in body and "release-publication" in body
    assert "30 days" in body and "20 days" in body
    assert "actions/runs/9" in body


def test_withdrawal_says_why_nothing_is_proposed() -> None:
    young = _facts() | {"today": "2026-11-05"}
    young["publications"] = [pub for pub in young["publications"] if pub["version"] in {"v0.30.1", "v0.29.2"}]
    comment = w.render_withdrawal(young, _pick(young), None)
    assert comment.startswith("No promotion is proposed any more: the oldest unpromoted pre-release is under 30 days old.")
    assert "v0.30.1 (16 days old)" in comment

    held = w.render_withdrawal(_facts(), _pick(_facts(), [{"number": 700, "found_in": None, "fixed_in": None}]), None)
    assert "no newer pre-release fixes" in held and "#700" in held


def _proposed(version: str = "0.30.2") -> dict:
    return {"propose": True, "version": version}


def test_a_proposal_opens_one_issue_when_none_is_open() -> None:
    assert w.plan_actions(_proposed(), [], "body", None) == [
        {"action": "create", "title": "Promotion proposed: v0.30.2", "body": "body"}
    ]


def test_a_proposal_updates_the_open_issue_and_closes_duplicates() -> None:
    open_issues = [{"number": 812, "title": "Promotion proposed: v0.30.2"}, {"number": 800, "title": "Promotion proposed: v0.30.1"}]
    actions = w.plan_actions(_proposed(), open_issues, "body", None)
    assert actions == [
        {"action": "edit", "number": 800, "title": "Promotion proposed: v0.30.2", "body": "body"},
        {"action": "comment", "number": 800, "comment": "The proposal changed from `Promotion proposed: v0.30.1` to `Promotion proposed: v0.30.2`."},
        {"action": "close", "number": 812, "comment": "Superseded by #800."},
    ]  # fmt: skip
    same = w.plan_actions(_proposed(), [{"number": 800, "title": "Promotion proposed: v0.30.2"}], "body", None)
    assert [action["action"] for action in same] == ["edit"]  # same version: no notification


def test_no_proposal_closes_every_open_proposal_with_the_reason() -> None:
    nothing = {"propose": False, "version": None}
    assert w.plan_actions(nothing, [{"number": 800, "title": "x"}], None, "why") == [
        {"action": "close", "number": 800, "comment": "why"}
    ]
    assert w.plan_actions(nothing, [], None, "why") == []


class _Gh:
    """Records `gh` calls; answers the open-proposal query and issue creation."""

    def __init__(self, open_issues: list[dict]) -> None:
        self.open_issues = open_issues
        self.calls: list[tuple[str, ...]] = []

    def api(self, path: str, jq: str, paginate: bool = True) -> list:
        assert path == "repos/o/r/issues?state=open&labels=promotion-proposal&per_page=100"
        return self.open_issues

    def run(self, *command: str) -> str:
        self.calls.append(command)
        return json.dumps({"number": 900, "labels": ["promotion-proposal"]})


def _propose(monkeypatch: pytest.MonkeyPatch, gh: _Gh, *, dry_run: bool, ref: str = "refs/heads/main", pick: dict | None = None) -> int:
    monkeypatch.setenv("DRY_RUN", str(dry_run).lower())
    monkeypatch.setenv("GITHUB_REF", ref)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", "")
    monkeypatch.setattr(pw, "_gh_api", gh.api)
    monkeypatch.setattr(pw, "_run", gh.run)
    facts = _facts()
    return w.propose(facts, pick or _pick(facts))


def test_a_dry_run_prints_the_proposal_and_changes_no_issue(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    gh = _Gh([{"number": 800, "title": "Promotion proposed: v0.30.0"}])
    assert _propose(monkeypatch, gh, dry_run=True, ref="refs/heads/feat/631") == 0
    assert gh.calls == []
    out = capsys.readouterr().out
    assert out.startswith("## Dry run: Promotion proposed: v0.30.1")
    assert "- edit #800" in out and "- comment #800" in out and "**v0.30.1**" in out


def test_a_real_run_opens_the_labelled_issue(monkeypatch: pytest.MonkeyPatch) -> None:
    gh = _Gh([])
    assert _propose(monkeypatch, gh, dry_run=False) == 0
    label, create = gh.calls
    assert label[:4] == ("gh", "label", "create", "promotion-proposal") and "--force" in label
    assert create[:5] == ("gh", "api", "-X", "POST", "repos/o/r/issues")
    assert "title=Promotion proposed: v0.30.1" in create and "labels[]=promotion-proposal" in create


def test_a_real_run_closes_a_stale_proposal_with_a_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    gh = _Gh([{"number": 800, "title": "Promotion proposed: v0.30.1"}])
    nothing = {"propose": False, "version": None, "age_days": None, "reason": "no-unpromoted-pre-release",
               "oldest_unpromoted": None, "blocked": []}  # fmt: skip
    assert _propose(monkeypatch, gh, dry_run=False, pick=nothing) == 0
    comment, close = gh.calls
    assert comment[-3:-1] == ("repos/o/r/issues/800/comments", "-f") and "No promotion is proposed" in comment[-1]
    assert close[-3:] == ("repos/o/r/issues/800", "-f", "state=closed")


def test_a_run_that_changes_issues_must_come_from_main(monkeypatch: pytest.MonkeyPatch) -> None:
    gh = _Gh([])
    with pytest.raises(SystemExit):
        _propose(monkeypatch, gh, dry_run=False, ref="refs/heads/feat/631")
    assert gh.calls == []


# --- Promotion ------------------------------------------------------------------

RELEASES = [
    _release("v0.30.2", "2026-11-01T00:00:00Z"),
    _release("v0.30.1", "2026-10-20T00:00:00Z", prerelease=False),
    _release("v0.30.0-rc.1", "2026-07-16T01:49:48Z"),
    _release("v0.30.4", draft=True),
]


@pytest.mark.parametrize(
    ("version", "ref", "refusal"),
    [
        ("0.30.2", "refs/heads/feat/x", "promotions run from refs/heads/main"),
        ("0.30.9", "refs/heads/main", "v0.30.9 is not a published pre-release"),
        ("0.30.4", "refs/heads/main", "v0.30.4 is not a published pre-release"),  # a draft
        ("0.30.1", "refs/heads/main", "v0.30.1 is already a release"),
        ("v0.30.0-rc.1", "refs/heads/main", "legacy -rc tags are never promoted"),
        ("0.30.2; rm -rf /", "refs/heads/main", "is not a plain version"),
        ("", "refs/heads/main", "is not a plain version"),
    ],
)
def test_promotion_is_refused(version: str, ref: str, refusal: str) -> None:
    assert any(refusal in blocker for blocker in w.promotion_blockers(version, RELEASES, ref))


def test_a_pre_release_not_newer_than_the_latest_release_is_refused() -> None:
    releases = [_release("v0.30.2"), _release("v0.30.3", prerelease=False)]
    assert w.promotion_blockers("0.30.2", releases, "refs/heads/main") == ["v0.30.2 is not newer than the latest release v0.30.3"]


def test_a_published_pre_release_newer_than_the_latest_release_may_be_promoted() -> None:
    assert w.promotion_blockers("0.30.2", RELEASES, "refs/heads/main") == []
    assert w.promotion_blockers(" v0.30.2 ", RELEASES, "refs/heads/main") == []
    assert w.tag_for(" v0.30.2 ") == "v0.30.2"


def _package(folder: Path, *, alias: bytes = b"zip", declared: str | None = None, missing: str | None = None) -> str:
    sha = hashlib.sha256(b"zip").hexdigest()
    files = {
        "CVMAnalytics-windows-v0.30.2.zip": b"zip",
        "CVMAnalytics-windows-v0.30.2.zip.sha256": f"{declared or sha}  CVMAnalytics-windows-v0.30.2.zip".encode(),
        "CVMAnalytics-windows.zip": alias,
        "CVMAnalytics-windows.zip.sha256": f"{hashlib.sha256(alias).hexdigest()}  CVMAnalytics-windows.zip".encode(),
    }
    for name, data in files.items():
        if name != missing:
            (folder / name).write_bytes(data)
    return sha


def test_the_published_package_is_re_verified(tmp_path: Path) -> None:
    sha = _package(tmp_path)
    assert w.package_blockers("v0.30.2", tmp_path) == (sha, [])


@pytest.mark.parametrize(
    ("over", "refusal"),
    [
        ({"declared": "0" * 64}, "CVMAnalytics-windows-v0.30.2.zip does not match its .sha256 file"),
        ({"alias": b"other"}, "CVMAnalytics-windows.zip is not the same bytes as CVMAnalytics-windows-v0.30.2.zip"),
        ({"missing": "CVMAnalytics-windows-v0.30.2.zip.sha256"}, "CVMAnalytics-windows-v0.30.2.zip or its .sha256 is missing"),
        ({"missing": "CVMAnalytics-windows.zip"}, "CVMAnalytics-windows.zip or its .sha256 is missing"),
    ],
)
def test_a_package_that_does_not_verify_is_refused(tmp_path: Path, over: dict, refusal: str) -> None:
    _package(tmp_path, **over)
    assert any(refusal in blocker for blocker in w.package_blockers("v0.30.2", tmp_path)[1])


def test_check_summary_is_the_approval_request() -> None:
    summary = w.render_check("v0.30.2", RELEASES, "f" * 64, [], TODAY)
    assert summary.startswith("## Promote v0.30.2 from pre-release to release")
    assert "26 days" in summary and "Latest release now: v0.30.1" in summary
    assert "f" * 64 in summary and "release-publication" in summary
    refused = w.render_check("v0.30.9", RELEASES, None, ["v0.30.9 is not a published pre-release"], TODAY)
    assert refused.startswith("## Promotion of v0.30.9 refused")


def _promote(monkeypatch: pytest.MonkeyPatch, *, latest_after: str = "v0.30.2", **package: object) -> tuple[int, list]:
    calls: list[tuple[str, ...]] = []

    def fake_run(*command: str) -> str:
        calls.append(command)
        if command[:3] == ("gh", "release", "download"):
            _package(Path(command[command.index("--dir") + 1]), **package)
        return ""

    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", "")
    monkeypatch.setattr(w, "_releases", lambda repo: RELEASES)
    monkeypatch.setattr(w, "_today", lambda: TODAY)
    monkeypatch.setattr(pw, "_run", fake_run)
    monkeypatch.setattr(pw, "_gh_api", lambda path, jq, paginate=True: [{"tag_name": latest_after}])
    return w.promote("0.30.2"), calls


def test_promotion_edits_the_same_release_into_the_latest_one(monkeypatch: pytest.MonkeyPatch) -> None:
    code, calls = _promote(monkeypatch)
    assert code == 0
    download, edit = calls
    assert download[:4] == ("gh", "release", "download", "v0.30.2")
    assert edit == ("gh", "release", "edit", "v0.30.2", "--repo", "o/r", "--prerelease=false", "--latest")
    assert not any("create" in call or "upload" in call for call in calls)  # same tag, same files


def test_promotion_stops_before_editing_when_the_package_does_not_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    code, calls = _promote(monkeypatch, alias=b"other")
    assert code == 1
    assert [call[:3] for call in calls] == [("gh", "release", "download")]


def test_promotion_fails_when_the_latest_release_does_not_read_back(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _promote(monkeypatch, latest_after="v0.30.1")[0] == 1
