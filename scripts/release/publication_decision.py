"""Publication decision for CVMAnalytics (ADR 0011, goal #623, issue #628).

Pure rules, no network and no git: the caller collects the facts and passes
them in as JSON. The publication workflow (`.github/workflows/release-desktop.yml`
through `publication_workflow.py`) calls `decide`; the promotion workflows
(#631) will call `promote`. Contract: `docs/release-process.md`.

Command line (JSON on stdin or `--input FILE`, JSON on stdout, exit 2 with a
message on stderr when the input is invalid):

    python scripts/release/publication_decision.py decide < facts.json
    python scripts/release/publication_decision.py promote < facts.json

`decide` input:

    {"last_publication": "v0.30.1" | null,
     "prs": [{"number": 640, "class": "pre", "title": "..."}],
     "changed_paths": ["desktop/updater.py"]}

`last_publication` is the published tag with the highest version (`v` prefix
optional, legacy `-rc.N` accepted); sort by version, not by name, or `v0.9.0`
wins over `v0.30.0`. `prs` and `changed_paths` are everything merged and
changed since that tag, not just the last PR; for a renamed file pass the old
and the new path. `class` is `none`, `pre`, `release` or
`hotfix` (the `ships:` label prefix is accepted); `null` marks a PR merged
before shipping classes existed and counts as `none`.

`decide` output: `publish`, `kind` (`pre-release` | `release` | null),
`shipping_class`, `version` (plain `MAJOR.MINOR.PATCH` | null),
`approval_required`, and `reasons` (`prs`, `class_prs`, `unclassified_prs`,
`risk_paths`, `approval`).

`promote` input:

    {"today": "2026-11-26",
     "publications": [{"version": "v0.30.1", "kind": "pre-release",
                       "published_at": "2026-10-20T12:00:00Z"}],
     "blocking_bugs": [{"number": 700, "found_in": "v0.30.2" | null,
                        "fixed_in": "v0.30.3" | null}]}

A blocking bug affects every publication from `found_in` (null: from the
start) up to, not including, `fixed_in` (null: not fixed).

`promote` output: `propose`, `version`, `age_days`, `reason`,
`oldest_unpromoted`, and `blocked` (pre-releases passed over, with bug numbers).

`prune` input (#634):

    {"publications": [{"version": "v0.30.1", "kind": "pre-release",
                       "assets": ["CVMAnalytics-windows.zip", "..."]}]}

`prune` output: `keep` (10), `kept` (the newest pre-releases, newest first), and
`prune` (`version` and `assets` of each older pre-release that still has
download files). Releases are never listed, so a promoted pre-release is never
pruned; nothing here removes a tag.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from fnmatch import fnmatchcase
from pathlib import Path

# Lowest to highest: the class of a publication is the highest among its PRs.
SHIPPING_CLASSES = ("none", "pre", "release", "hotfix")
KIND_BY_CLASS = {"pre": "pre-release", "release": "release", "hotfix": "release"}
FIRST_VERSION = (0, 30, 0)
PROMOTION_TRIGGER_DAYS = 30
PROMOTION_MIN_AGE_DAYS = 20
# Pre-releases that keep their download files; the owner accepted 10 on 2026-11-26 (#634).
RETENTION_KEEP = 10

# The one list of risk areas. A changed path matching any pattern makes a
# pre-release wait for the owner's approval. `*` also matches `/`. The first
# matching area names the path, so the narrower areas come before `desktop/*`.
RISK_AREAS: dict[str, tuple[str, ...]] = {
    "packaging and build scripts": (
        "desktop/app.spec",
        "desktop/build_desktop.ps1",
        ".github/workflows/release-desktop.yml",
        "scripts/release/publication_workflow.py",
    ),
    "dependency manifests": (
        "requirements.txt",
        "apps/desktop-web/package.json",
        "apps/desktop-web/package-lock.json",
    ),
    # Tables are created next to the code that uses them, so the modules holding
    # CREATE/ALTER TABLE are listed one by one; a test fails when one is missing.
    "database schema and migrations": (
        "src/platform/db.py",
        "src/financials/database.py",
        "src/*schema*",
        "src/*migrat*",
        "src/companies/b3_classification.py",
        "src/companies/classification.py",
        "src/companies/coverage.py",
        "src/companies/market_history.py",
        "src/companies/universe.py",
        "src/energy_kpi/distribution/mmgd_store.py",
        "src/energy_kpi/fuel_distribution.py",
        "src/financials/excel_mapping.py",
        "src/financials/marts.py",
        "scripts/setup/setup_db.py",
        "scripts/setup/setup_companies_table.py",
    ),
    "ingestion and refresh": (
        "src/refresh/*",
        "src/*ingest*",
        "src/*refresh*",
        "src/*scraper*",
        "src/companies/catalog.py",
        "src/companies/market_cap.py",
        "src/news/fetcher.py",
    ),
    "desktop shell, bridge and updater": ("desktop/*",),
}

_NUMBER = r"(0|[1-9][0-9]*)"
_VERSION_RE = re.compile(rf"v?{_NUMBER}\.{_NUMBER}\.{_NUMBER}(?:-rc\.{_NUMBER})?")


def parse_version(tag: object) -> tuple[int, int, int, int | None]:
    """Read `0.30.1`, `v0.30.1` or a legacy `v0.30.0-rc.1` tag."""
    match = _VERSION_RE.fullmatch(tag) if isinstance(tag, str) else None
    if match is None:
        raise ValueError(f"not a publication version: {tag!r}")
    major, minor, patch, rc = match.groups()
    return int(major), int(minor), int(patch), None if rc is None else int(rc)


def _order(version: tuple[int, int, int, int | None]) -> tuple[int, ...]:
    major, minor, patch, rc = version
    return major, minor, patch, rc is None, rc or 0  # an -rc.N sorts before its plain number


def _plain(version: tuple) -> str:
    return ".".join(str(part) for part in version[:3])


def _next_version(last: tuple[int, int, int, int | None] | None, shipping_class: str) -> str:
    if last is None:
        return _plain(FIRST_VERSION)
    major, minor, patch, rc = last
    if rc is not None:
        bumped = (major, minor, patch)  # the -rc.N announced this number; it was never published plain
    elif shipping_class == "release":
        bumped = (major, minor + 1, 0)
    else:
        bumped = (major, minor, patch + 1)
    return _plain(max(bumped, FIRST_VERSION))


def _shipping_class(value: object) -> str | None:
    if value is None:
        return None
    name = value.removeprefix("ships:") if isinstance(value, str) else value
    if name not in SHIPPING_CLASSES:
        raise ValueError(f"unknown shipping class: {value!r}")
    return name


def _risk_paths(changed_paths: list[str]) -> list[dict]:
    # A bare string would be read letter by letter and match no risk area.
    if isinstance(changed_paths, str) or not all(isinstance(raw, str) for raw in changed_paths):
        raise ValueError("changed_paths must be a list of path strings")
    found = []
    for path in sorted({raw.replace("\\", "/").removeprefix("./") for raw in changed_paths}):
        for area, patterns in RISK_AREAS.items():
            if any(fnmatchcase(path, pattern) for pattern in patterns):
                found.append({"path": path, "area": area})
                break
    return found


def decide_publication(last_publication: str | None, prs: list[dict], changed_paths: list[str]) -> dict:
    last = None if last_publication is None else parse_version(last_publication)
    listed = [
        {"number": pr["number"], "class": _shipping_class(pr.get("class")), "title": pr.get("title")}
        for pr in prs
    ]
    shipping_class = max((pr["class"] or "none" for pr in listed), key=SHIPPING_CLASSES.index, default="none")
    kind = KIND_BY_CLASS.get(shipping_class)
    risk_paths = _risk_paths(changed_paths)

    approval = []
    if kind == "release":
        approval.append("every release needs the owner's approval")
    if kind and risk_paths:
        approval.append("changes since the last publication touch a risk area")

    return {
        "publish": kind is not None,
        "kind": kind,
        "shipping_class": shipping_class,
        "version": _next_version(last, shipping_class) if kind else None,
        "approval_required": bool(approval),
        "reasons": {
            "prs": listed,
            "class_prs": [pr["number"] for pr in listed if kind and pr["class"] == shipping_class],
            "unclassified_prs": [pr["number"] for pr in listed if pr["class"] is None],
            "risk_paths": risk_paths,
            "approval": approval,
        },
    }


def _day(value: object) -> date:
    return date.fromisoformat(str(value)[:10])  # a date or an ISO timestamp


def pick_promotion(publications: list[dict], blocking_bugs: list[dict], today: str) -> dict:
    now = _day(today)
    releases, waiting = [], []
    for pub in publications:
        version = parse_version(pub["version"])
        entry = {"order": _order(version), "version": _plain(version), "age_days": (now - _day(pub["published_at"])).days}
        if pub["kind"] == "release":
            releases.append(entry)
        elif pub["kind"] != "pre-release":
            raise ValueError(f"unknown publication kind: {pub['kind']!r}")
        elif version[3] is None:  # legacy -rc.N tags are predecessors only, never promoted
            waiting.append(entry)

    # Builds are cumulative: a release covers every pre-release at or below it.
    newest_release = max((entry["order"] for entry in releases), default=())
    waiting = sorted((entry for entry in waiting if entry["order"] > newest_release), key=lambda e: e["order"])
    bugs = [
        (
            bug["number"],
            _order(parse_version(bug["found_in"])) if bug.get("found_in") else (),
            _order(parse_version(bug["fixed_in"])) if bug.get("fixed_in") else None,
        )
        for bug in blocking_bugs
    ]

    def label(entry: dict) -> dict:
        return {"version": entry["version"], "age_days": entry["age_days"]}

    def answer(reason: str, picked: dict | None = None, oldest: dict | None = None, blocked: list | None = None) -> dict:
        return {
            "propose": picked is not None,
            "version": picked and picked["version"],
            "age_days": picked and picked["age_days"],
            "reason": reason,
            "oldest_unpromoted": oldest and label(oldest),
            "blocked": blocked or [],
        }

    if not waiting:
        return answer("no-unpromoted-pre-release")
    oldest = max(waiting, key=lambda e: e["age_days"])
    if oldest["age_days"] < PROMOTION_TRIGGER_DAYS:
        return answer("oldest-pre-release-under-30-days", oldest=oldest)

    # Never empty: `oldest` itself is old enough.
    chosen = [entry for entry in waiting if entry["age_days"] >= PROMOTION_MIN_AGE_DAYS][-1]
    blocked = []
    for entry in waiting[waiting.index(chosen):]:
        hit = [
            number
            for number, found, fixed in bugs
            if found <= entry["order"] and (fixed is None or entry["order"] < fixed)
        ]
        if not hit:
            reason = "time-rule" if entry is chosen else "blocking-bug-fixed-in-newer-pre-release"
            return answer(reason, picked=entry, oldest=oldest, blocked=blocked)
        blocked.append({**label(entry), "blocking_bugs": hit})
    return answer("blocking-bug-not-fixed", oldest=oldest, blocked=blocked)


def pick_pruning(publications: list[dict], keep: int = RETENTION_KEEP) -> dict:
    pre_releases = []
    for pub in publications:
        if pub["kind"] not in ("pre-release", "release"):
            raise ValueError(f"unknown publication kind: {pub['kind']!r}")
        if pub["kind"] == "pre-release":  # legacy -rc.N tags count too: they are on the releases page
            pre_releases.append((_order(parse_version(pub["version"])), pub["version"], sorted(pub["assets"])))
    pre_releases.sort(key=lambda item: item[0], reverse=True)
    return {
        "keep": keep,
        "kept": [version for _, version, _ in pre_releases[:keep]],
        "prune": [
            {"version": version, "assets": assets}
            for _, version, assets in pre_releases[keep:]
            if assets  # already pruned: nothing to do, so a re-run is a no-op
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publication decision and promotion pick (ADR 0011).")
    parser.add_argument("command", choices=("decide", "promote", "prune"))
    parser.add_argument("--input", default="-", help="JSON file with the facts; '-' (default) reads stdin")
    args = parser.parse_args(argv)
    try:
        # Bytes, not text: a Windows runner would otherwise decode PR titles as cp1252.
        raw = sys.stdin.buffer.read() if args.input == "-" else Path(args.input).read_bytes()
        facts = json.loads(raw.decode("utf-8-sig"))
        if args.command == "decide":
            result = decide_publication(facts["last_publication"], facts["prs"], facts["changed_paths"])
        elif args.command == "promote":
            result = pick_promotion(facts["publications"], facts["blocking_bugs"], facts["today"])
        else:
            result = pick_pruning(facts["publications"])
    except (KeyError, TypeError, ValueError, AttributeError, OSError) as exc:
        print(f"invalid input: {exc!r}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
