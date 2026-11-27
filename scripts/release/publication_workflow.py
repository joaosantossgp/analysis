"""Glue for the publication workflow (ADR 0011, goal #623, issue #629).

`.github/workflows/release-desktop.yml` runs these three commands. The rules
themselves live in `publication_decision.py`; this file only collects the facts
that module needs, reports its answer, and publishes the built candidate.

    python scripts/release/publication_workflow.py facts > facts.json
    python scripts/release/publication_decision.py decide --input facts.json > decision.json
    python scripts/release/publication_workflow.py report --facts facts.json --decision decision.json
    python scripts/release/publication_workflow.py publish --facts facts.json --decision decision.json \
        --package-dir candidate --expected-sha256 <ZIP hash from the build job> \
        --expected-setup-sha256 <installer hash from the build job>

`facts` and `publish` call `git` and `gh` (GH_TOKEN, GITHUB_REPOSITORY and
GITHUB_REF come from the workflow). DRY_RUN=true collects the facts for the
checked-out commit instead of `main`, and makes `publish` stop before the
release is created. ASSUME_CLASS is honored in a dry run only.

The last publication is the published GitHub release with the highest version,
never a bare tag: a candidate that was rejected or superseded leaves no trace,
so the next decision still counts everything since the last real publication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # run as a script or imported as scripts.release.*
import publication_decision as pd  # noqa: E402

MAIN_REF = "refs/heads/main"
# Same closing keywords as the PR check in .github/workflows/pr-issue-guardrails.yml.
_CLOSING = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)
_MERGE_SUBJECT = re.compile(r"^Merge pull request #(\d+) |\(#(\d+)\)$")
_PLAIN_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_SHA = re.compile(r"[0-9a-f]{40}")
_PATHS_SHOWN = 15


# --- Pure rules ----------------------------------------------------------------

def last_publication(releases: list[dict]) -> str | None:
    """Tag of the published (non-draft) release with the highest version."""
    published = []
    for release in releases:
        if release.get("draft"):
            continue
        try:
            published.append((pd._order(pd.parse_version(release["tag_name"])), release["tag_name"]))
        except ValueError:
            continue  # a release that is not a publication of the app
    return max(published)[1] if published else None


def pick_candidate(shas: list[str], ci_runs: list[dict]) -> str | None:
    """Newest commit (shas are newest first) whose latest push/main CI run is green."""
    latest: dict[str, dict] = {}
    for run in sorted(ci_runs, key=lambda r: (r["created_at"], r.get("run_attempt") or 1)):
        latest[run["head_sha"]] = run
    for sha in shas:
        run = latest.get(sha)
        if run and run["status"] == "completed" and run["conclusion"] == "success":
            return sha
    return None


def classes_by_issue(issues_by_class: dict[str, list[int]]) -> dict[int, str]:
    """Issue number -> its highest `ships:*` class."""
    result: dict[int, str] = {}
    for name in pd.SHIPPING_CLASSES:  # lowest to highest, so the highest label wins
        for number in issues_by_class.get(name, []):
            result[number] = name
    return result


def merged_prs(subjects: list[str], pulls: list[dict], class_by_issue: dict[int, str]) -> list[dict]:
    """PRs merged on the first-parent path, each with the class of the issues it closes.

    A PR that closes no classified issue gets class None (merged before shipping
    classes existed); the decision module counts it as `none` and reports it.
    """
    by_number = {pull["number"]: pull for pull in pulls}
    listed: dict[int, dict] = {}
    for subject in subjects:
        match = _MERGE_SUBJECT.search(subject)
        pull = by_number.get(int(match.group(1) or match.group(2))) if match else None
        if pull is None or pull["number"] in listed:
            continue
        closed = {int(number) for number in _CLOSING.findall(pull.get("body") or "")}
        classes = [class_by_issue[number] for number in closed if number in class_by_issue]
        listed[pull["number"]] = {
            "number": pull["number"],
            "class": max(classes, key=pd.SHIPPING_CLASSES.index, default=None),
            "title": pull["title"],
        }
    return list(listed.values())


def _pr_lines(prs: list[dict], with_class: bool) -> list[str]:
    lines = []
    for pr in prs:
        if not pr["number"]:  # the synthetic entry of a dry run with ASSUME_CLASS
            continue
        suffix = f" (`{pr['class'] or 'unclassified'}`)" if with_class else ""
        lines.append(f"- #{pr['number']} {pr['title']}{suffix}")
    return lines


def render_summary(facts: dict, decision: dict) -> str:
    """Job summary. For a publication that needs approval, this is the approval request."""
    reasons = decision["reasons"]
    prefix = "Dry run: " if facts["dry_run"] else ""
    lines: list[str] = []
    if not decision["publish"]:
        lines.append(f"## {prefix}Nothing to publish")
        if facts["candidate_sha"] is None:
            lines.append(f"No commit on `main` after {facts['last_publication']} has a green CI run yet.")
        else:
            lines.append(
                f"Every PR merged since {facts['last_publication']} has shipping class `none`, so no candidate is built."
            )
    else:
        lines.append(f"## {prefix}Publication {decision['version']} ({decision['kind']})")
        if decision["approval_required"]:
            lines.append(
                "**Waits for the owner's approval** in the `release-publication` environment: "
                + "; ".join(reasons["approval"])
                + "."
            )
        else:
            lines.append("**Publishes with no approval**: a pre-release whose changes stay outside the risk areas.")
    lines.append("")
    lines.append(f"- Candidate commit: `{facts['candidate_sha']}`")
    lines.append(f"- Previous publication: {facts['last_publication']}")
    lines.append(f"- Shipping class: `{decision['shipping_class']}`")
    if facts["dry_run"]:
        lines.append("- Dry run: nothing is tagged or published.")
        if facts.get("assumed_class"):
            lines.append(f"- Shipping class `{facts['assumed_class']}` was assumed for this dry run, not read from labels.")
        if not facts.get("ci_green"):
            lines.append("- CI is not green for this commit on `main`; a real run would not build it.")

    by_area: dict[str, list[str]] = {}
    for risk in reasons["risk_paths"]:
        by_area.setdefault(risk["area"], []).append(risk["path"])
    lines += ["", "### Risk areas touched", ""]
    if not by_area:
        lines.append("None.")
    for area, paths in by_area.items():
        shown = ", ".join(f"`{path}`" for path in paths[:_PATHS_SHOWN])
        more = f" and {len(paths) - _PATHS_SHOWN} more" if len(paths) > _PATHS_SHOWN else ""
        lines.append(f"- **{area}** ({len(paths)}): {shown}{more}")

    pr_lines = _pr_lines(reasons["prs"], with_class=True)
    lines += ["", f"### Merged PRs since {facts['last_publication']} ({len(pr_lines)})", ""]
    lines += pr_lines or ["None."]
    return "\n".join(lines) + "\n"


def render_notes(facts: dict, decision: dict) -> str:
    """Body of the publication page: what it is and the merged PRs it contains."""
    kind = decision["kind"].capitalize()
    lines = [
        f"{kind} {decision['version']}, built once from `main` at `{facts['candidate_sha']}`. "
        "It contains everything published before it.",
        "",
        f"## Merged pull requests since {facts['last_publication']}",
        "",
    ]
    lines += _pr_lines(decision["reasons"]["prs"], with_class=False) or ["None."]
    return "\n".join(lines) + "\n"


def job_outputs(facts: dict, decision: dict) -> dict[str, str]:
    """Values the later jobs read. Shapes are checked here because they end up in commands and file names."""
    version = decision["version"] or ""
    sha = facts["candidate_sha"] or ""
    if decision["publish"] and not (_PLAIN_VERSION.fullmatch(version) and _SHA.fullmatch(sha)):
        raise ValueError(f"refusing a malformed version or commit: {version!r}, {sha!r}")
    return {
        "publish": str(bool(decision["publish"])).lower(),
        "kind": decision["kind"] or "",
        "version": version,
        "approval_required": str(bool(decision["approval_required"])).lower(),
        "candidate_sha": sha,
        "dry_run": str(bool(facts["dry_run"])).lower(),
    }


def publish_blockers(
    *,
    facts: dict,
    decision: dict,
    releases: list[dict],
    tag_exists: bool,
    on_main: bool,
    ref: str,
    actual_sha256: str,
    declared_sha256: str,
    expected_sha256: str,
    setup_actual_sha256: str,
    setup_declared_sha256: str,
    setup_expected_sha256: str,
    dry_run: bool,
) -> list[str]:
    """Every reason the candidate must not be published now. Empty means publish."""
    blockers = []
    if not decision["publish"]:
        blockers.append("the decision says there is nothing to publish")
    for name, actual, declared, expected in (
        ("ZIP", actual_sha256, declared_sha256, expected_sha256),
        ("installer", setup_actual_sha256, setup_declared_sha256, setup_expected_sha256),
    ):
        if actual != declared:
            blockers.append(f"the {name} does not match its .sha256 file")
        if actual != expected:
            blockers.append(f"the {name} is not the file the build job produced")
    current = last_publication(releases)
    if current != facts["last_publication"]:
        blockers.append(
            f"stale candidate: it was decided after {facts['last_publication']}, but {current} is published now"
        )
    tag = f"v{decision['version']}"
    if tag_exists or any(r["tag_name"] == tag and not r.get("draft") for r in releases):
        blockers.append(f"{tag} already exists")
    if not dry_run:
        if facts["dry_run"]:
            blockers.append("the facts were collected in a dry run")
        if ref != MAIN_REF:
            blockers.append(f"publications run from {MAIN_REF}, not {ref}")
        if not on_main:
            blockers.append("the candidate commit is not on main")
    return blockers


def release_command(facts: dict, decision: dict, notes_file: str, files: list[str]) -> list[str]:
    pre = decision["kind"] == "pre-release"
    return [
        "gh", "release", "create", f"v{decision['version']}",
        "--repo", facts["repository"],
        "--target", facts["candidate_sha"],  # the tag is created here, on the exact commit, with the release
        "--title", f"CVM Analytics v{decision['version']}",
        "--notes-file", notes_file,
        *(["--prerelease"] if pre else []),
        f"--latest={'false' if pre else 'true'}",
        *files,
    ]  # fmt: skip


# --- git and gh ----------------------------------------------------------------

def _run(*command: str) -> str:
    return subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8").stdout


def _git(*args: str) -> str:
    return _run("git", "-c", "core.quotePath=false", *args).strip()


def _gh_api(path: str, jq: str, paginate: bool = True) -> list:
    """One JSON value per output line of `gh api --jq`.

    `--jq` prints strings raw, so the filter must yield numbers or objects.
    """
    out = _run("gh", "api", path, *(["--paginate"] if paginate else []), "--jq", jq)
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def _releases(repo: str) -> list[dict]:
    return _gh_api(f"repos/{repo}/releases?per_page=100", ".[] | {id, tag_name, draft, prerelease}")


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() == "true"


def collect_facts() -> dict:
    repo = os.environ["GITHUB_REPOSITORY"]
    dry_run = _flag("DRY_RUN")
    assumed = os.environ.get("ASSUME_CLASS", "").strip() or None
    if assumed is not None and assumed not in pd.SHIPPING_CLASSES:
        raise SystemExit(f"ASSUME_CLASS must be one of {', '.join(pd.SHIPPING_CLASSES)}, not {assumed!r}")
    if not dry_run:
        if os.environ.get("GITHUB_REF") != MAIN_REF:
            raise SystemExit(f"a real publication run must come from {MAIN_REF}")
        if assumed:
            raise SystemExit("ASSUME_CLASS is for dry runs only")

    last = last_publication(_releases(repo))
    if last is None:
        raise SystemExit("no published release found, so 'since the last publication' cannot be computed")
    head = _git("rev-parse", "HEAD")
    if subprocess.run(["git", "merge-base", "--is-ancestor", f"{last}^{{commit}}", head]).returncode != 0:
        raise SystemExit(f"{last} is not an ancestor of {head}")

    ci_runs = _gh_api(
        f"repos/{repo}/actions/workflows/ci.yml/runs?branch=main&event=push&per_page=100",
        ".workflow_runs[] | {head_sha, status, conclusion, created_at, run_attempt}",
        paginate=False,
    )
    if dry_run:
        candidate = head
    else:
        candidate = pick_candidate(_git("rev-list", "--first-parent", f"{last}..{head}").split(), ci_runs)

    prs: list[dict] = []
    changed_paths: list[str] = []
    if candidate:
        subjects = _git("log", "--first-parent", "--format=%s", f"{last}..{candidate}").splitlines()
        pulls = _gh_api(
            f"repos/{repo}/pulls?state=closed&base=main&per_page=100",
            ".[] | select(.merged_at != null) | {number, title, body}",
        )
        issues_by_class = {
            name: _gh_api(f"repos/{repo}/issues?state=all&labels=ships:{name}&per_page=100", ".[].number")
            for name in pd.SHIPPING_CLASSES
        }
        prs = merged_prs(subjects, pulls, classes_by_issue(issues_by_class))
        changed_paths = _git("diff", "--name-only", "--no-renames", last, candidate).splitlines()
    if assumed:
        prs.insert(0, {"number": 0, "class": assumed, "title": "dry run: assumed shipping class"})

    return {
        "repository": repo,
        "dry_run": dry_run,
        "assumed_class": assumed,
        "last_publication": last,
        "candidate_sha": candidate,
        "ci_green": bool(candidate) and pick_candidate([candidate], ci_runs) == candidate,
        "prs": prs,
        "changed_paths": changed_paths,
    }


def _declared_sha256(path: Path) -> str:
    return path.with_name(f"{path.name}.sha256").read_text(encoding="utf-8-sig").split()[0].lower()


def publish(facts: dict, decision: dict, package_dir: Path, expected_sha256: str, expected_setup_sha256: str) -> int:
    repo = facts["repository"]
    dry_run = _flag("DRY_RUN")
    tag = f"v{decision['version']}"
    package = package_dir / f"CVMAnalytics-windows-{tag}.zip"
    setup = package_dir / f"CVMAnalytics-Setup-{tag}.exe"
    actual = hashlib.sha256(package.read_bytes()).hexdigest()
    setup_actual = hashlib.sha256(setup.read_bytes()).hexdigest()
    releases = _releases(repo)

    blockers = publish_blockers(
        facts=facts,
        decision=decision,
        releases=releases,
        tag_exists=any(  # matching-refs matches by prefix: v0.30.0 also returns v0.30.0-rc.1
            ref["ref"] == f"refs/tags/{tag}"
            for ref in _gh_api(f"repos/{repo}/git/matching-refs/tags/{tag}", ".[] | {ref}")
        ),
        on_main=subprocess.run(
            ["git", "merge-base", "--is-ancestor", facts["candidate_sha"], "origin/main"]
        ).returncode == 0,
        ref=os.environ.get("GITHUB_REF", ""),
        actual_sha256=actual,
        declared_sha256=_declared_sha256(package),
        expected_sha256=expected_sha256.strip().lower(),
        setup_actual_sha256=setup_actual,
        setup_declared_sha256=_declared_sha256(setup),
        setup_expected_sha256=expected_setup_sha256.strip().lower(),
        dry_run=dry_run,
    )
    if blockers:
        print("Not published:\n- " + "\n- ".join(blockers), file=sys.stderr)
        return 1

    # Unversioned aliases: same bytes under the fixed names that older installs,
    # README.md and the landing page (releases/latest/download/...) use.
    files: list[str] = []
    for versioned, alias_name, sha256 in (
        (package, "CVMAnalytics-windows.zip", actual),
        (setup, "CVMAnalytics-Setup.exe", setup_actual),
    ):
        alias = package_dir / alias_name
        shutil.copyfile(versioned, alias)
        alias.with_name(f"{alias_name}.sha256").write_text(f"{sha256}  {alias_name}", encoding="utf-8")
        files += [str(versioned), f"{versioned}.sha256", str(alias), f"{alias}.sha256"]
    notes = package_dir / "publication-notes.md"
    notes.write_text(render_notes(facts, decision), encoding="utf-8")
    command = release_command(facts, decision, str(notes), files)

    print(f"Verified candidate {package.name} sha256 {actual}")
    print(f"Verified installer {setup.name} sha256 {setup_actual}")
    if dry_run:
        print("Dry run: stopping before the tag and the release. Would run:\n  " + " ".join(command))
        print("\n" + notes.read_text(encoding="utf-8"))
        return 0
    # A publish step cancelled during upload leaves a draft for this tag; it was never visible.
    for release in releases:
        if release["tag_name"] == tag and release.get("draft"):
            _run("gh", "api", "-X", "DELETE", f"repos/{repo}/releases/{release['id']}")
    subprocess.run(command, check=True)
    print(f"Published {tag} as a {decision['kind']} from {facts['candidate_sha']}")
    return 0


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publication workflow glue (ADR 0011).")
    parser.add_argument("command", choices=("facts", "report", "publish"))
    parser.add_argument("--facts")
    parser.add_argument("--decision")
    parser.add_argument("--package-dir")
    parser.add_argument("--expected-sha256", default="")
    parser.add_argument("--expected-setup-sha256", default="")
    args = parser.parse_args(argv)

    if args.command == "facts":
        sys.stdout.buffer.write(json.dumps(collect_facts(), indent=2).encode("utf-8"))
        return 0
    facts, decision = _load(args.facts), _load(args.decision)
    if args.command == "publish":
        return publish(facts, decision, Path(args.package_dir), args.expected_sha256, args.expected_setup_sha256)

    summary = render_summary(facts, decision)
    outputs = job_outputs(facts, decision)
    sys.stdout.buffer.write(summary.encode("utf-8"))
    for variable, text in (
        ("GITHUB_STEP_SUMMARY", summary),
        ("GITHUB_OUTPUT", "".join(f"{key}={value}\n" for key, value in outputs.items())),
    ):
        if os.environ.get(variable):
            with open(os.environ[variable], "a", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
