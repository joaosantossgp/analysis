from __future__ import annotations

import json

import pytest

from scripts.release import publication_decision as pd
from scripts.release import publication_workflow as pw


def _release(tag: str, *, draft: bool = False, prerelease: bool = False) -> dict:
    return {"id": abs(hash(tag)) % 10_000, "tag_name": tag, "draft": draft, "prerelease": prerelease}


def _ci(sha: str, conclusion: str | None = "success", *, status: str = "completed", created_at: str = "2026-11-26T10:00:00Z", attempt: int = 1) -> dict:
    return {"head_sha": sha, "status": status, "conclusion": conclusion, "created_at": created_at, "run_attempt": attempt}


# --- Last publication ----------------------------------------------------------

def test_last_publication_is_the_highest_published_version_not_the_last_by_name() -> None:
    releases = [_release("v0.9.0"), _release("v0.30.0-rc.1", prerelease=True), _release("v0.29.2"), _release("v0.30.0")]
    assert pw.last_publication(releases) == "v0.30.0"


def test_last_publication_ignores_drafts_and_tags_that_are_not_versions() -> None:
    releases = [_release("v0.30.2", draft=True), _release("nightly"), _release("v0.30.1", prerelease=True)]
    assert pw.last_publication(releases) == "v0.30.1"
    assert pw.last_publication([_release("v0.30.2", draft=True)]) is None


# --- Candidate commit ----------------------------------------------------------

def test_candidate_is_the_newest_commit_with_green_main_ci() -> None:
    runs = [_ci("c3", "failure"), _ci("c2"), _ci("c1")]
    assert pw.pick_candidate(["c3", "c2", "c1"], runs) == "c2"


def test_candidate_needs_the_latest_run_of_its_commit_to_be_green() -> None:
    rerun_failed = [_ci("c1", created_at="2026-11-26T10:00:00Z"), _ci("c1", "failure", created_at="2026-11-26T11:00:00Z")]
    assert pw.pick_candidate(["c1"], rerun_failed) is None
    assert pw.pick_candidate(["c1"], [_ci("c1", None, status="in_progress")]) is None
    assert pw.pick_candidate(["c1"], []) is None
    assert pw.pick_candidate([], [_ci("c1")]) is None


# --- Merged PRs and their shipping class ---------------------------------------

def test_shipping_class_of_issues_takes_the_highest_label() -> None:
    assert pw.classes_by_issue({"none": [10, 11], "pre": [11, 12], "release": [], "hotfix": [12]}) == {
        10: "none",
        11: "pre",
        12: "hotfix",
    }


def test_merged_prs_come_from_first_parent_subjects_with_the_class_of_closed_issues() -> None:
    subjects = [
        "Merge pull request #640 from joaosantossgp/feat/626-update-channel",
        "Squashed fix for the pill (#639)",
        "Merge pull request #638 from joaosantossgp/docs/x",
        "Merge pull request #637 from joaosantossgp/feat/legacy",
        "Direct commit that mentions (#12)",
        "Merge pull request #640 from joaosantossgp/feat/626-update-channel",
    ]
    pulls = [
        {"number": 640, "title": "Update channel", "body": "Closes #626\nFixes #700\nRefs #623"},
        {"number": 639, "title": "Pill fix", "body": "resolves #701"},
        {"number": 638, "title": "Docs", "body": "Closes #702\nRefs #626"},
        {"number": 637, "title": "Legacy", "body": None},
    ]
    class_by_issue = {626: "pre", 700: "hotfix", 701: "none", 623: "release"}

    assert pw.merged_prs(subjects, pulls, class_by_issue) == [
        {"number": 640, "class": "hotfix", "title": "Update channel"},
        {"number": 639, "class": "none", "title": "Pill fix"},
        {"number": 638, "class": None, "title": "Docs"},  # closes an unclassified issue; Refs never count
        {"number": 637, "class": None, "title": "Legacy"},
    ]


def test_merged_prs_feed_the_decision_module() -> None:
    prs = pw.merged_prs(
        ["Merge pull request #640 from o/b"],
        [{"number": 640, "title": "Update channel", "body": "Closes #626"}],
        {626: "pre"},
    )
    decision = pd.decide_publication("v0.30.0-rc.1", prs, ["apps/desktop-web/src/x.tsx"])
    assert (decision["publish"], decision["version"], decision["approval_required"]) == (True, "0.30.0", False)


# --- Approval request and publication page -------------------------------------

def _facts(**over: object) -> dict:
    facts = {
        "repository": "o/r",
        "dry_run": False,
        "assumed_class": None,
        "last_publication": "v0.30.0",
        "candidate_sha": "a" * 40,
        "ci_green": True,
        "prs": [
            {"number": 640, "class": "pre", "title": "Update channel"},
            {"number": 638, "class": None, "title": "Docs"},
        ],
        "changed_paths": ["desktop/updater.py", "requirements.txt", "docs/x.md"],
    }
    return facts | over


def _decision(facts: dict) -> dict:
    return pd.decide_publication(facts["last_publication"], facts["prs"], facts["changed_paths"])


def test_summary_states_version_prs_and_risk_areas_for_the_approval_request() -> None:
    facts = _facts()
    summary = pw.render_summary(facts, _decision(facts))

    assert "0.30.1" in summary and "pre-release" in summary
    assert "release-publication" in summary  # where the owner approves
    assert "#640 Update channel" in summary and "#638 Docs" in summary
    assert "desktop shell, bridge and updater" in summary and "`desktop/updater.py`" in summary
    assert "dependency manifests" in summary
    assert "a" * 40 in summary and "v0.30.0" in summary


def test_summary_says_when_nothing_is_published_or_it_publishes_alone() -> None:
    nothing = _facts(prs=[{"number": 638, "class": "none", "title": "Docs"}])
    assert "Nothing to publish" in pw.render_summary(nothing, _decision(nothing))

    automatic = _facts(changed_paths=["docs/x.md"])
    summary = pw.render_summary(automatic, _decision(automatic))
    assert "no approval" in summary and "release-publication" not in summary

    no_candidate = _facts(candidate_sha=None, prs=[], changed_paths=[])
    assert "no commit" in pw.render_summary(no_candidate, _decision(no_candidate)).lower()


def test_summary_marks_a_dry_run() -> None:
    facts = _facts(dry_run=True, assumed_class="pre", ci_green=False)
    summary = pw.render_summary(facts, _decision(facts))
    assert summary.startswith("## Dry run")
    assert "assumed" in summary and "not green" in summary


def test_notes_list_the_merged_prs_of_the_publication() -> None:
    facts = _facts(prs=[{"number": 0, "class": "pre", "title": "dry run"}, {"number": 640, "class": "pre", "title": "Update channel"}])
    notes = pw.render_notes(facts, _decision(facts))
    assert "- #640 Update channel" in notes
    assert "#0" not in notes
    assert "a" * 40 in notes and "Pre-release" in notes


# --- Job outputs ---------------------------------------------------------------

def test_outputs_carry_the_decision_and_refuse_a_malformed_version() -> None:
    facts = _facts()
    decision = _decision(facts)
    assert pw.job_outputs(facts, decision) == {
        "publish": "true",
        "kind": "pre-release",
        "version": "0.30.1",
        "approval_required": "true",
        "candidate_sha": "a" * 40,
        "dry_run": "false",
    }
    with pytest.raises(ValueError):
        pw.job_outputs(facts, decision | {"version": "0.30.1; rm -rf"})
    with pytest.raises(ValueError):
        pw.job_outputs(facts | {"candidate_sha": "main"}, decision)

    nothing = _facts(prs=[])
    assert pw.job_outputs(nothing, _decision(nothing))["publish"] == "false"


# --- Publish-time checks -------------------------------------------------------

def _blockers(**over: object) -> list[str]:
    facts = over.pop("facts", _facts())
    args = {
        "facts": facts,
        "decision": _decision(facts),
        "releases": [_release("v0.30.0"), _release("v0.29.2")],
        "tag_exists": False,
        "on_main": True,
        "ref": "refs/heads/main",
        "actual_sha256": "f" * 64,
        "declared_sha256": "f" * 64,
        "expected_sha256": "f" * 64,
        "dry_run": False,
    }
    return pw.publish_blockers(**(args | over))


def test_a_current_verified_candidate_has_no_blockers() -> None:
    assert _blockers() == []


@pytest.mark.parametrize(
    "over",
    [
        {"actual_sha256": "0" * 64},  # not the file the build job produced
        {"declared_sha256": "0" * 64},
        {"expected_sha256": ""},
        {"releases": [_release("v0.30.1"), _release("v0.30.0")]},  # something was published since the decision
        {"tag_exists": True},
        {"on_main": False},
        {"ref": "refs/heads/feature"},
        {"facts": _facts(dry_run=True)},  # a dry-run decision is never published
        {"facts": _facts(prs=[])},  # the decision says do not publish
    ],
)
def test_publication_is_refused(over: dict) -> None:
    assert _blockers(**over)


def test_a_draft_left_by_an_interrupted_publish_does_not_block() -> None:
    assert _blockers(releases=[_release("v0.30.1", draft=True), _release("v0.30.0")]) == []


def test_dry_run_skips_only_the_main_branch_checks() -> None:
    dry = _facts(dry_run=True)
    assert _blockers(facts=dry, dry_run=True, on_main=False, ref="refs/heads/feature") == []
    assert _blockers(facts=dry, dry_run=True, actual_sha256="0" * 64)


def test_release_command_targets_the_exact_commit_with_the_decided_kind() -> None:
    facts = _facts()
    pre = pw.release_command(facts, _decision(facts), "notes.md", ["a.zip", "a.zip.sha256"])
    assert pre[:4] == ["gh", "release", "create", "v0.30.1"]
    assert pre[pre.index("--target") + 1] == "a" * 40
    assert "--prerelease" in pre and "--latest=false" in pre
    assert pre[-2:] == ["a.zip", "a.zip.sha256"]

    release_facts = _facts(prs=[{"number": 650, "class": "release", "title": "Big"}])
    release = pw.release_command(release_facts, _decision(release_facts), "notes.md", [])
    assert release[3] == "v0.31.0"
    assert "--prerelease" not in release and "--latest=true" in release


def test_facts_file_is_accepted_by_the_decision_cli(tmp_path, capsys) -> None:
    path = tmp_path / "facts.json"
    path.write_text(json.dumps(_facts()), encoding="utf-8")
    assert pd.main(["decide", "--input", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["version"] == "0.30.1"
