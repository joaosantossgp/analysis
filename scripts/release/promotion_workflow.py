"""Glue for promotion (ADR 0011, goal #623, issue #631).

The promotion rule (30-day trigger, newest pre-release at least 20 days old,
blocking-bug exception) lives in `publication_decision.py promote`; this file
collects the facts it needs, keeps the one proposal issue current, and verifies
and performs a promotion. Contract: `docs/release-process.md`.

Promotion (`.github/workflows/promote-release.yml`, dispatched by the owner):

    python scripts/release/promotion_workflow.py verify --version 0.30.1   # read-only, before approval
    python scripts/release/promotion_workflow.py promote --version 0.30.1  # after approval

Proposal (`.github/workflows/promotion-proposal.yml`, daily; it never promotes):

    python scripts/release/promotion_workflow.py facts > facts.json
    python scripts/release/publication_decision.py promote --input facts.json > pick.json
    python scripts/release/promotion_workflow.py propose --facts facts.json --pick pick.json

Retention (`.github/workflows/prerelease-retention.yml`, after each Release
Desktop run and weekly, issue #634): the newest 10 pre-releases keep their
download files; older pre-releases lose them, and their tags and pages stay.

    python scripts/release/promotion_workflow.py prune

Commands call `gh` and `git` (GH_TOKEN, GITHUB_REPOSITORY and GITHUB_REF come
from the workflow). A promotion, and a proposal or retention run without
DRY_RUN=true, refuse any ref but `main`. DRY_RUN=true makes `propose` print the
issue changes, and `prune` the files it would remove, instead of making them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # run as a script or imported as scripts.release.*
import publication_decision as pd  # noqa: E402
import publication_workflow as pw  # noqa: E402

LABEL = "promotion-proposal"
TITLE_PREFIX = "Promotion proposed: "
ALIAS = "CVMAnalytics-windows.zip"
ADR = "docs/decisions/0011-build-once-publications-and-update-channels.md"
# `publication_workflow.render_notes` lists each PR as `- #640 Title`.
_NOTES_PR = re.compile(r"^- #(\d+) (.+?)\s*$", re.MULTILINE)
# A "Version" field in a bug body: `Version: 0.30.2`, or an issue-form heading `### Version` with the value below.
# shortcut: the bug form has no Version field yet, so found_in is null unless someone writes that line;
# add the field to .github/ISSUE_TEMPLATE/bug.yml if blocking bugs become common.
_BUG_VERSION = re.compile(r"^[ \t]*(?:#+[ \t]*)?Version[ \t]*:?\s*(v?[0-9][0-9A-Za-z.-]*)", re.IGNORECASE | re.MULTILINE)
_CLOSER_QUERY = """query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) { issue(number: $number) {
    timelineItems(itemTypes: CLOSED_EVENT, last: 1) { nodes { ... on ClosedEvent {
      closer { ... on PullRequest { mergeCommit { oid } } ... on Commit { oid } } } } } } } }"""

_PROPOSED_BECAUSE = {
    "time-rule": "the oldest unpromoted pre-release is at least 30 days old, and this is the newest "
    "pre-release at least 20 days old.",
    "blocking-bug-fixed-in-newer-pre-release": "the pre-release the time rule chose has a blocking bug, "
    "and this is the first newer pre-release without one.",
}
_NOTHING_BECAUSE = {
    "no-unpromoted-pre-release": "no pre-release is waiting; every published pre-release is covered by a release.",
    "oldest-pre-release-under-30-days": "the oldest unpromoted pre-release is under 30 days old.",
    "blocking-bug-not-fixed": "every pre-release old enough to promote has a blocking bug that no newer "
    "pre-release fixes.",
}


# --- Pure rules ----------------------------------------------------------------

def _order(tag: str) -> tuple[int, ...]:
    return pd._order(pd.parse_version(tag))


def tag_for(version: str) -> str | None:
    """`v0.30.1` for `0.30.1` or `v0.30.1`; None for anything else, legacy `-rc.N` tags included."""
    try:
        parsed = pd.parse_version(version.strip())
    except ValueError:
        return None
    return None if parsed[3] is not None else f"v{pd._plain(parsed)}"


def latest_release(releases: list[dict]) -> str | None:
    """Tag of the published release (not pre-release) with the highest version."""
    return pw.last_publication([release for release in releases if not release.get("prerelease")])


def notes_prs(body: str | None) -> list[dict]:
    return [{"number": int(number), "title": title} for number, title in _NOTES_PR.findall(body or "")]


def publications(releases: list[dict]) -> list[dict]:
    """Published app releases in the shape `publication_decision.py promote` reads, with their notes' PRs."""
    found = []
    for release in releases:
        if release.get("draft"):
            continue
        try:
            pd.parse_version(release["tag_name"])
        except ValueError:
            continue  # a release that is not a publication of the app
        found.append({
            "version": release["tag_name"],
            "kind": "pre-release" if release.get("prerelease") else "release",
            "published_at": release["published_at"],
            "prs": notes_prs(release.get("body")),
            "assets": list(release.get("assets") or []),
        })
    return found


def found_in(body: str | None) -> str | None:
    match = _BUG_VERSION.search(body or "")
    if match is None:
        return None
    try:
        pd.parse_version(match.group(1))
    except ValueError:
        return None
    return match.group(1)


def blocking_bug(issue: dict, closing_commit: str | None, fixing_tags: list[str], published: set[str]) -> dict | None:
    """A `bug` + `priority:p0` issue as a blocking bug of the promotion pick, or None when it blocks nothing.

    Open: it blocks every pre-release. Closed by a PR (or commit): fixed in the
    earliest published version whose tag contains that commit; until one does,
    it still blocks. `fixing_tags` are the tags that contain `closing_commit`.
    """
    if issue["state"] == "open":
        # shortcut: an open bug blocks every pre-release, even one older than its Version line;
        # read found_in for open bugs too if that ever holds back a good promotion.
        return {"number": issue["number"], "found_in": None, "fixed_in": None}
    # shortcut: a p0 bug closed as not planned, or closed by hand with no closing PR, blocks nothing;
    # if hand-closed fixes turn out to matter, record the fix PR on the issue and read it here.
    if issue.get("state_reason") == "not_planned" or not closing_commit:
        return None
    fixed = [tag for tag in fixing_tags if tag in published]
    return {
        "number": issue["number"],
        "found_in": found_in(issue.get("body")),
        "fixed_in": min(fixed, key=_order) if fixed else None,
    }


def promotion_blockers(version: str, releases: list[dict], ref: str) -> list[str]:
    """Every reason `version` must not be promoted now. Empty means it may be."""
    blockers = [] if ref == pw.MAIN_REF else [f"promotions run from {pw.MAIN_REF}, not {ref or 'an unknown ref'}"]
    tag = tag_for(version)
    if tag is None:
        return blockers + [f"{version!r} is not a plain version like 0.30.1 (legacy -rc tags are never promoted)"]
    release = next((r for r in releases if r["tag_name"] == tag and not r.get("draft")), None)
    if release is None:
        blockers.append(f"{tag} is not a published pre-release")
    elif not release.get("prerelease"):
        blockers.append(f"{tag} is already a release")
    latest = latest_release(releases)
    if latest and _order(tag) <= _order(latest):
        blockers.append(f"{tag} is not newer than the latest release {latest}")
    return blockers


def package_blockers(tag: str, folder: Path) -> tuple[str | None, list[str]]:
    """SHA-256 of the versioned ZIP, and every reason the downloaded files are not one verified package."""
    package = f"CVMAnalytics-windows-{tag}.zip"
    hashes: dict[str, str] = {}
    blockers = []
    for name in (package, ALIAS):
        checksum = folder / f"{name}.sha256"
        if not (folder / name).is_file() or not checksum.is_file():
            blockers.append(f"{name} or its .sha256 is missing from the release")
            continue
        hashes[name] = hashlib.sha256((folder / name).read_bytes()).hexdigest()
        declared = checksum.read_text(encoding="utf-8-sig").split()
        if not declared or declared[0].lower() != hashes[name]:
            blockers.append(f"{name} does not match its .sha256 file")
    if len(hashes) == 2 and hashes[package] != hashes[ALIAS]:
        blockers.append(f"{ALIAS} is not the same bytes as {package}")
    return hashes.get(package), blockers


def render_check(tag: str | None, releases: list[dict], sha256: str | None, blockers: list[str], today: str) -> str:
    """Job summary of a promotion check. Before approval, this is the approval request."""
    release = next((r for r in releases if r["tag_name"] == tag and not r.get("draft")), None)
    if blockers:
        lines = [f"## Promotion of {tag or 'this version'} refused", ""] + [f"- {blocker}" for blocker in blockers]
        return "\n".join(lines) + "\n"
    age = (pd._day(today) - pd._day(release["published_at"])).days
    return "\n".join([
        f"## Promote {tag} from pre-release to release",
        "",
        "Same tag and same files: nothing is rebuilt or renumbered. After the owner's approval in the "
        f"`release-publication` environment, {tag} becomes the latest release and installed apps on "
        "\"releases only\" are offered it.",
        "",
        f"- Pre-release since {release['published_at'][:10]} ({age} days)",
        f"- Latest release now: {latest_release(releases) or 'none'}",
        f"- `CVMAnalytics-windows-{tag}.zip` sha256 `{sha256}` matches its `.sha256`; "
        f"`{ALIAS}` is the same bytes",
        f"- Publication page and the PRs it contains: {release.get('html_url') or tag}",
    ]) + "\n"


def render_proposal(facts: dict, pick: dict, run_url: str | None) -> str:
    """Body of the proposal issue."""
    tag = f"v{pick['version']}"
    oldest = pick["oldest_unpromoted"]
    latest = facts.get("latest_release")
    lines = [
        f"The time rule proposes promoting **{tag}** from pre-release to release.",
        "",
        f"- Version: {tag}, a pre-release for {pick['age_days']} days",
        f"- Oldest unpromoted pre-release: v{oldest['version']} ({oldest['age_days']} days old)",
        f"- Latest release now: {latest or 'none'}",
        f"- Why this one: {_PROPOSED_BECAUSE.get(pick['reason'], pick['reason'])}",
    ]
    for passed in pick["blocked"]:
        bugs = ", ".join(f"#{number}" for number in passed["blocking_bugs"])
        lines.append(f"- Passed over: v{passed['version']} ({passed['age_days']} days old), blocking bug {bugs}")

    # Builds are cumulative: the release carries every pre-release since the latest release, up to this one.
    floor = _order(latest) if latest else ()
    carried = sorted(
        (pub for pub in facts["publications"]
         if pub["kind"] == "pre-release" and floor < _order(pub["version"]) <= _order(tag)),
        key=lambda pub: _order(pub["version"]),
        reverse=True,
    )
    lines += ["", f"### Pull requests it contains since {latest or 'the first publication'}", ""]
    for pub in carried:
        lines.append(f"**[{pub['version']}](https://github.com/{facts['repository']}/releases/tag/{pub['version']})**")
        lines += [f"- #{pr['number']} {pr['title']}" for pr in pub["prs"]] or ["- No pull requests listed in its notes."]
        lines.append("")
    lines += [
        "### Next step",
        "",
        f"To promote, the owner runs the **Promote Release** workflow (`promote-release.yml`) from `main` with "
        f"version `{pick['version']}` and approves the `release-publication` deployment. This issue only "
        "proposes; nothing is promoted without that approval.",
        "",
        f"Rule ([ADR 0011](https://github.com/{facts['repository']}/blob/main/{ADR})): when the oldest unpromoted "
        "pre-release is 30 days old, the newest pre-release at least 20 days old is proposed; if it has a "
        "blocking bug (`bug` + `priority:p0`), the first newer pre-release without one is proposed instead.",
        "",
        f"_Updated {facts['today']} by the Promotion Proposal workflow" + (f" ({run_url})" if run_url else "") + "._",
    ]
    return "\n".join(lines) + "\n"


def render_withdrawal(facts: dict, pick: dict, run_url: str | None) -> str:
    """Comment that closes a proposal that no longer applies."""
    text = f"No promotion is proposed any more: {_NOTHING_BECAUSE.get(pick['reason'], pick['reason'])}"
    if pick["oldest_unpromoted"]:
        oldest = pick["oldest_unpromoted"]
        text += f" Oldest unpromoted pre-release: v{oldest['version']} ({oldest['age_days']} days old)."
    for passed in pick["blocked"]:
        bugs = ", ".join(f"#{number}" for number in passed["blocking_bugs"])
        text += f" v{passed['version']} is held by blocking bug {bugs}."
    return text + f" Checked {facts['today']}" + (f" ({run_url})" if run_url else "") + "."


def plan_actions(pick: dict, open_issues: list[dict], body: str | None, withdrawal: str | None) -> list[dict]:
    """Issue changes that leave exactly one open proposal when there is a pick, and none otherwise."""
    issues = sorted(open_issues, key=lambda issue: issue["number"])
    if not pick["propose"]:
        return [{"action": "close", "number": issue["number"], "comment": withdrawal} for issue in issues]
    title = f"{TITLE_PREFIX}v{pick['version']}"
    if not issues:
        return [{"action": "create", "title": title, "body": body}]
    keep, *extra = issues
    actions = [{"action": "edit", "number": keep["number"], "title": title, "body": body}]
    if keep["title"] != title:  # an edit notifies nobody; a comment does
        actions.append({"action": "comment", "number": keep["number"], "comment": f"The proposal changed from `{keep['title']}` to `{title}`."})
    actions += [
        {"action": "close", "number": issue["number"], "comment": f"Superseded by #{keep['number']}."}
        for issue in extra
    ]
    return actions


def render_summary(pick: dict, actions: list[dict], text: str, dry_run: bool) -> str:
    prefix = "Dry run: " if dry_run else ""
    heading = f"{TITLE_PREFIX}v{pick['version']}" if pick["propose"] else "No promotion proposed"
    lines = [f"## {prefix}{heading}", "", "Issue changes" + (" (not made: dry run)" if dry_run else "") + ":", ""]
    lines += [
        f"- {action['action']} " + (f"#{action['number']}" if "number" in action else f"`{action['title']}`")
        for action in actions
    ] or ["- none"]
    return "\n".join(lines + ["", "---", "", text]) + "\n"


# --- gh and git ----------------------------------------------------------------

def _releases(repo: str) -> list[dict]:
    return pw._gh_api(
        f"repos/{repo}/releases?per_page=100",
        ".[] | {id, tag_name, draft, prerelease, published_at, html_url, body, assets: [.assets[].name]}",
    )


def _closing_commit(repo: str, number: int) -> str | None:
    """Merge commit of the PR (or the commit) that closed the issue. REST leaves it null for PR merges."""
    owner, name = repo.split("/")
    out = pw._run(
        "gh", "api", "graphql", "-f", f"query={_CLOSER_QUERY}", "-f", f"owner={owner}", "-f", f"name={name}",
        "-F", f"number={number}",
        "--jq", ".data.repository.issue.timelineItems.nodes[0].closer | .mergeCommit.oid // .oid // empty",
    )  # fmt: skip
    return out.strip() or None


def _tags_containing(commit: str) -> list[str]:
    result = subprocess.run(["git", "tag", "--contains", commit], capture_output=True, text=True)
    return result.stdout.split() if result.returncode == 0 else []  # a commit unknown here is in no tag


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _run_url() -> str | None:
    server, repo, run = (os.environ.get(name) for name in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"{server}/{repo}/actions/runs/{run}" if server and repo and run else None


def _report(text: str) -> None:
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.flush()
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8", newline="\n") as handle:
            handle.write(text)


def collect_facts() -> dict:
    repo = os.environ["GITHUB_REPOSITORY"]
    releases = _releases(repo)
    published = publications(releases)
    published_tags = {pub["version"] for pub in published}
    bugs = []
    for issue in pw._gh_api(
        f"repos/{repo}/issues?state=all&labels=bug,priority:p0&per_page=100",  # both labels
        ".[] | select(.pull_request == null) | {number, state, state_reason, body}",
    ):
        commit = _closing_commit(repo, issue["number"]) if issue["state"] == "closed" else None
        bug = blocking_bug(issue, commit, _tags_containing(commit) if commit else [], published_tags)
        if bug:
            bugs.append(bug)
    return {
        "repository": repo,
        "today": _today(),
        "latest_release": latest_release(releases),
        "publications": published,
        "blocking_bugs": bugs,
    }


def _apply(repo: str, action: dict) -> None:
    api = ("gh", "api", "--silent", "-X")
    issue = f"repos/{repo}/issues/{action.get('number')}"
    if action["action"] == "create":
        pw._run("gh", "label", "create", LABEL, "--repo", repo, "--force", "--color", "5319E7",
                "--description", "Promotion proposed by the scheduled promotion check (ADR 0011)")  # fmt: skip
        created = json.loads(pw._run(
            "gh", "api", "-X", "POST", f"repos/{repo}/issues", "-f", f"title={action['title']}",
            "-f", f"body={action['body']}", "-f", f"labels[]={LABEL}", "--jq", "{number, labels: [.labels[].name]}",
        ))  # fmt: skip
        if LABEL not in created["labels"]:  # a label the token may not set is dropped silently; next run would not find it
            pw._run(*api, "POST", f"repos/{repo}/issues/{created['number']}/labels", "-f", f"labels[]={LABEL}")
        print(f"Opened #{created['number']}")
    elif action["action"] == "edit":
        pw._run(*api, "PATCH", issue, "-f", f"title={action['title']}", "-f", f"body={action['body']}")
        print(f"Updated #{action['number']}")
    else:
        pw._run(*api, "POST", f"{issue}/comments", "-f", f"body={action['comment']}")
        if action["action"] == "close":
            pw._run(*api, "PATCH", issue, "-f", "state=closed")
        print(f"{action['action']}: #{action['number']}")


def propose(facts: dict, pick: dict) -> int:
    repo = facts["repository"]
    dry_run = pw._flag("DRY_RUN")
    if not dry_run and os.environ.get("GITHUB_REF") != pw.MAIN_REF:
        raise SystemExit(f"a proposal run that changes issues must come from {pw.MAIN_REF}; use a dry run elsewhere")
    run_url = _run_url()
    body = render_proposal(facts, pick, run_url) if pick["propose"] else None
    withdrawal = None if pick["propose"] else render_withdrawal(facts, pick, run_url)
    open_issues = pw._gh_api(
        f"repos/{repo}/issues?state=open&labels={LABEL}&per_page=100",
        ".[] | select(.pull_request == null) | {number, title}",
    )
    actions = plan_actions(pick, open_issues, body, withdrawal)
    _report(render_summary(pick, actions, body or withdrawal, dry_run))
    if not dry_run:
        for action in actions:
            _apply(repo, action)
    return 0


def render_pruning(plan: dict, dry_run: bool) -> str:
    verb = "Would remove" if dry_run else "Removing"
    lines = [
        f"## {'Dry run: ' if dry_run else ''}Pre-release retention",
        "",
        f"The newest {plan['keep']} pre-releases keep their download files: {', '.join(plan['kept']) or 'none'}.",
        "Releases, tags and release pages are never touched.",
        "",
    ]
    lines += [f"- {verb} {len(entry['assets'])} files from {entry['version']}: {', '.join(entry['assets'])}" for entry in plan["prune"]]
    if not plan["prune"]:
        lines.append("Nothing to remove.")
    return "\n".join(lines) + "\n"


def prune() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    dry_run = pw._flag("DRY_RUN")
    if not dry_run and os.environ.get("GITHUB_REF") != pw.MAIN_REF:
        raise SystemExit(f"a retention run that removes files must come from {pw.MAIN_REF}; use a dry run elsewhere")
    plan = pd.pick_pruning(publications(_releases(repo)))
    _report(render_pruning(plan, dry_run))
    if not dry_run:
        for entry in plan["prune"]:
            for asset in entry["assets"]:
                pw._run("gh", "release", "delete-asset", entry["version"], asset, "--repo", repo, "--yes")
                print(f"Removed {asset} from {entry['version']}")
    return 0


def verify(version: str, folder: Path) -> tuple[str | None, list[str]]:
    repo = os.environ["GITHUB_REPOSITORY"]
    releases = _releases(repo)
    tag = tag_for(version)
    blockers = promotion_blockers(version, releases, os.environ.get("GITHUB_REF", ""))
    sha256 = None
    if not blockers:
        patterns = [f"CVMAnalytics-windows-{tag}.zip", ALIAS]
        patterns += [f"{name}.sha256" for name in patterns]
        pw._run("gh", "release", "download", tag, "--repo", repo, "--dir", str(folder),
                *(argument for pattern in patterns for argument in ("--pattern", pattern)))  # fmt: skip
        sha256, blockers = package_blockers(tag, folder)
    _report(render_check(tag, releases, sha256, blockers, _today()))
    return tag, blockers


def promote(version: str) -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    with tempfile.TemporaryDirectory() as folder:
        tag, blockers = verify(version, Path(folder))  # again: things may have changed while approval waited
    if blockers:
        print("Not promoted:\n- " + "\n- ".join(blockers), file=sys.stderr)
        return 1
    pw._run("gh", "release", "edit", tag, "--repo", repo, "--prerelease=false", "--latest")
    latest = pw._gh_api(f"repos/{repo}/releases/latest", "{tag_name}", paginate=False)
    if [entry["tag_name"] for entry in latest] != [tag]:
        print(f"Edited {tag}, but the latest release reads back as {latest}", file=sys.stderr)
        return 1
    print(f"Promoted {tag} to the latest release: same tag, same files")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Promotion workflow glue (ADR 0011).")
    parser.add_argument("command", choices=("verify", "promote", "facts", "propose", "prune"))
    parser.add_argument("--version", default="")
    parser.add_argument("--facts")
    parser.add_argument("--pick")
    args = parser.parse_args(argv)

    try:
        if args.command == "facts":
            sys.stdout.buffer.write(json.dumps(collect_facts(), indent=2).encode("utf-8"))
            return 0
        if args.command == "propose":
            return propose(pw._load(args.facts), pw._load(args.pick))
        if args.command == "promote":
            return promote(args.version)
        if args.command == "prune":
            return prune()
        with tempfile.TemporaryDirectory() as folder:
            return 1 if verify(args.version, Path(folder))[1] else 0
    except subprocess.CalledProcessError as exc:  # gh or git failed: show why, the output was captured
        print(f"{exc.cmd[:3]} failed ({exc.returncode}): {exc.stderr}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
