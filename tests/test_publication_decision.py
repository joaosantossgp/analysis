from __future__ import annotations

import io
import json

import pytest

from scripts.release import publication_decision as pd


def _prs(*classes: str | None) -> list[dict]:
    return [{"number": 100 + i, "class": cls} for i, cls in enumerate(classes)]


# --- Class resolution and kind -------------------------------------------------

@pytest.mark.parametrize(
    ("classes", "publish", "shipping_class", "kind"),
    [
        ((), False, "none", None),
        (("none",), False, "none", None),
        (("none", "none"), False, "none", None),
        ((None,), False, "none", None),
        (("pre",), True, "pre", "pre-release"),
        (("none", "pre", "none"), True, "pre", "pre-release"),
        (("pre", "release"), True, "release", "release"),
        (("release", "hotfix", "pre"), True, "hotfix", "release"),
        (("hotfix",), True, "hotfix", "release"),
        (("ships:pre", "ships:none"), True, "pre", "pre-release"),
    ],
)
def test_class_is_highest_since_last_publication(classes, publish, shipping_class, kind) -> None:
    result = pd.decide_publication("v0.30.0", _prs(*classes), [])
    assert result["publish"] is publish
    assert result["shipping_class"] == shipping_class
    assert result["kind"] == kind
    assert (result["version"] is not None) is publish


def test_no_publication_needs_no_approval_even_with_risk_paths() -> None:
    result = pd.decide_publication("v0.30.0", _prs("none"), ["desktop/updater.py"])
    assert result["publish"] is False
    assert result["approval_required"] is False
    assert result["version"] is None
    # The pending risky change stays visible: it will hold the next publication.
    assert [item["path"] for item in result["reasons"]["risk_paths"]] == ["desktop/updater.py"]


@pytest.mark.parametrize("bad", ["prerelease", "ships:major", "", 3])
def test_unknown_class_is_rejected(bad) -> None:
    with pytest.raises(ValueError):
        pd.decide_publication("v0.30.0", [{"number": 1, "class": bad}], [])


# --- Version -------------------------------------------------------------------

@pytest.mark.parametrize(
    ("last", "shipping_class", "expected"),
    [
        (None, "pre", "0.30.0"),
        (None, "release", "0.30.0"),
        (None, "hotfix", "0.30.0"),
        # Tags published before this scheme are predecessors of 0.30.0.
        ("v0.29.2", "pre", "0.30.0"),
        ("v0.29.2", "release", "0.30.0"),
        ("v0.30.0-rc.1", "pre", "0.30.0"),
        ("v0.30.0-rc.1", "release", "0.30.0"),
        ("v0.30.0-rc.1", "hotfix", "0.30.0"),
        ("v0.31.0-rc.2", "pre", "0.31.0"),
        ("v0.30.0", "pre", "0.30.1"),
        ("v0.30.0", "hotfix", "0.30.1"),
        ("v0.30.0", "release", "0.31.0"),
        ("0.30.9", "pre", "0.30.10"),
        ("v0.30.9", "release", "0.31.0"),
        ("v1.4.2", "release", "1.5.0"),
    ],
)
def test_next_version(last, shipping_class, expected) -> None:
    assert pd.decide_publication(last, _prs(shipping_class), [])["version"] == expected


@pytest.mark.parametrize("bad", ["latest", "v0.30", "v0.30.0-beta.1", "v0.30.0-rc.1-3-gabc1234", "v01.2.3"])
def test_malformed_last_publication_is_rejected(bad) -> None:
    with pytest.raises(ValueError):
        pd.decide_publication(bad, _prs("pre"), [])


# --- Approval and risk areas ---------------------------------------------------

@pytest.mark.parametrize(
    "path",
    [
        "desktop/app.py",
        "desktop/bridge.py",
        "desktop/bridge_api/refresh.py",
        "desktop/updater.py",
        "desktop/update_helper.ps1",
        "desktop/app.spec",
        "desktop/build_desktop.ps1",
        ".github/workflows/release-desktop.yml",
        "requirements.txt",
        "apps/desktop-web/package.json",
        "apps/desktop-web/package-lock.json",
        "src/platform/db.py",
        "src/financials/database.py",
        "src/energy_kpi/schema.py",
        "src/companies/entity_registry_schema.py",
        "src/refresh/service.py",
        "src/financials/scraper.py",
        "src/financials/refresh_commands.py",
        "src/energy_kpi/distribution/ingest.py",
        "src/energy_kpi/sin_ingest.py",
        "src/platform/managed_ingestion_registry.py",
        "src/financials/marts.py",
        "src/companies/coverage.py",
        "src/companies/market_cap.py",
        "src/news/fetcher.py",
        "desktop\\updater.py",
        "./desktop/updater.py",
    ],
)
def test_pre_release_touching_a_risk_area_needs_approval(path) -> None:
    result = pd.decide_publication("v0.30.0", _prs("pre"), ["README.md", path])
    assert result["kind"] == "pre-release"
    assert result["approval_required"] is True
    risk = result["reasons"]["risk_paths"]
    assert len(risk) == 1
    assert risk[0]["path"] == path.replace("\\", "/").removeprefix("./")
    assert risk[0]["area"] in pd.RISK_AREAS


@pytest.mark.parametrize(
    "paths",
    [
        [],
        ["README.md", "docs/release-process.md"],
        ["apps/desktop-web/src/App.tsx", "src/financials/kpi_engine.py"],
        ["tests/test_updater.py", "scripts/release/publication_decision.py"],
        ["apps/api/requirements.txt", ".github/workflows/ci.yml"],
    ],
)
def test_pre_release_outside_risk_areas_publishes_without_approval(paths) -> None:
    result = pd.decide_publication("v0.30.0", _prs("pre"), paths)
    assert result["publish"] is True
    assert result["approval_required"] is False
    assert result["reasons"]["risk_paths"] == []
    assert result["reasons"]["approval"] == []


@pytest.mark.parametrize("shipping_class", ["release", "hotfix"])
@pytest.mark.parametrize("paths", [[], ["README.md"], ["desktop/updater.py"]])
def test_every_release_needs_approval(shipping_class, paths) -> None:
    result = pd.decide_publication("v0.30.0", _prs(shipping_class), paths)
    assert result["kind"] == "release"
    assert result["approval_required"] is True


@pytest.mark.parametrize("bad", ["desktop/updater.py", [["desktop/updater.py"]], [None]])
def test_changed_paths_must_be_a_list_of_strings(bad) -> None:
    # A bare string must not be read as "no risk path".
    with pytest.raises(ValueError):
        pd.decide_publication("v0.30.0", _prs("pre"), bad)


def test_every_schema_or_fetch_module_in_src_is_a_risk_path() -> None:
    """Keeps RISK_AREAS honest: tables and downloads live in modules whose names do not say so."""
    import re
    from pathlib import Path

    root = Path(pd.__file__).resolve().parents[2]
    marker = re.compile(
        r"CREATE\s+(?:VIRTUAL\s+)?TABLE|ALTER\s+TABLE|^\s*(?:import|from)\s+(?:requests|httpx)\b", re.I | re.M
    )
    risky = [
        path.relative_to(root).as_posix()
        for path in sorted((root / "src").rglob("*.py"))
        if marker.search(path.read_text(encoding="utf-8", errors="replace"))
    ]
    assert len(risky) > 10
    covered = {item["path"] for item in pd.decide_publication(None, [], risky)["reasons"]["risk_paths"]}
    assert sorted(set(risky) - covered) == [], "add these modules to RISK_AREAS in scripts/release/publication_decision.py"


def test_risk_is_judged_on_everything_since_the_last_publication() -> None:
    # A `none` PR changed the updater earlier; the later `pre` PR is docs-only.
    prs = [
        {"number": 640, "class": "none", "title": "Refactor updater"},
        {"number": 641, "class": "pre", "title": "Add export column"},
    ]
    result = pd.decide_publication("v0.30.1", prs, ["desktop/updater.py", "src/financials/excel_exporter.py"])
    assert result["approval_required"] is True
    assert result["version"] == "0.30.2"


def test_reasons_name_the_prs_and_risk_paths() -> None:
    prs = [
        {"number": 650, "class": "ships:pre", "title": "Small fix"},
        {"number": 651, "class": "release", "title": "Valuation workspace"},
        {"number": 652, "class": None, "title": "Merged before labels existed"},
        {"number": 653, "class": "none"},
    ]
    result = pd.decide_publication("v0.30.4", prs, ["requirements.txt", "desktop/updater.py", "README.md"])
    reasons = result["reasons"]
    assert result["version"] == "0.31.0"
    assert reasons["prs"] == [
        {"number": 650, "class": "pre", "title": "Small fix"},
        {"number": 651, "class": "release", "title": "Valuation workspace"},
        {"number": 652, "class": None, "title": "Merged before labels existed"},
        {"number": 653, "class": "none", "title": None},
    ]
    assert reasons["class_prs"] == [651]
    assert reasons["unclassified_prs"] == [652]
    assert reasons["risk_paths"] == [
        {"path": "desktop/updater.py", "area": "desktop shell, bridge and updater"},
        {"path": "requirements.txt", "area": "dependency manifests"},
    ]
    assert len(reasons["approval"]) == 2
    json.dumps(result)  # machine-readable


def test_risk_areas_are_one_list_covering_the_five_areas() -> None:
    assert sorted(pd.RISK_AREAS) == [
        "database schema and migrations",
        "dependency manifests",
        "desktop shell, bridge and updater",
        "ingestion and refresh",
        "packaging and build scripts",
    ]
    assert all(patterns for patterns in pd.RISK_AREAS.values())


@pytest.mark.parametrize(
    ("path", "area"),
    [
        ("desktop/app.spec", "packaging and build scripts"),
        ("desktop/build_desktop.ps1", "packaging and build scripts"),
        ("desktop/updater.py", "desktop shell, bridge and updater"),
        ("requirements.txt", "dependency manifests"),
        ("src/news/schema.py", "database schema and migrations"),
        ("src/refresh/jobs.py", "ingestion and refresh"),
    ],
)
def test_risk_path_is_named_by_its_narrowest_area(path, area) -> None:
    result = pd.decide_publication("v0.30.0", _prs("pre"), [path])
    assert result["reasons"]["risk_paths"] == [{"path": path, "area": area}]


# --- Promotion pick ------------------------------------------------------------

TODAY = "2026-11-26"


def _pub(version: str, age_days: int, kind: str = "pre-release") -> dict:
    from datetime import date, timedelta

    published = date.fromisoformat(TODAY) - timedelta(days=age_days)
    return {"version": version, "kind": kind, "published_at": f"{published.isoformat()}T09:30:00Z"}


RELEASE = _pub("v0.30.0", 60, "release")


@pytest.mark.parametrize(
    ("publications", "bugs", "version", "reason"),
    [
        # Empty cases.
        ([], [], None, "no-unpromoted-pre-release"),
        ([RELEASE], [], None, "no-unpromoted-pre-release"),
        # Pre-releases at or below the newest release are already covered by it.
        ([_pub("v0.30.1", 50), _pub("v0.30.2", 40, "release")], [], None, "no-unpromoted-pre-release"),
        # Legacy -rc.N tags are predecessors only: never proposed, never start the clock.
        ([_pub("v0.29.2", 140, "release"), _pub("v0.30.0-rc.1", 133)], [], None, "no-unpromoted-pre-release"),
        # 30-day trigger.
        ([RELEASE, _pub("v0.30.1", 29)], [], None, "oldest-pre-release-under-30-days"),
        ([RELEASE, _pub("v0.30.1", 29), _pub("v0.30.2", 21)], [], None, "oldest-pre-release-under-30-days"),
        ([RELEASE, _pub("v0.30.1", 30)], [], "0.30.1", "time-rule"),
        # Newest pre-release at least 20 days old; younger ones wait.
        ([RELEASE, _pub("v0.30.1", 35), _pub("v0.30.2", 20), _pub("v0.30.3", 19)], [], "0.30.2", "time-rule"),
        ([RELEASE, _pub("v0.30.1", 35), _pub("v0.30.2", 25), _pub("v0.30.3", 20)], [], "0.30.3", "time-rule"),
        ([_pub("v0.30.1", 45), _pub("v0.30.2", 5)], [], "0.30.1", "time-rule"),
        # Blocking bug fixed in a newer pre-release: propose the newer one, even if young.
        (
            [RELEASE, _pub("v0.30.1", 35), _pub("v0.30.2", 22), _pub("v0.30.3", 4)],
            [{"number": 700, "found_in": "v0.30.2", "fixed_in": "v0.30.3"}],
            "0.30.3",
            "blocking-bug-fixed-in-newer-pre-release",
        ),
        # The first newer pre-release that is clean, not the newest.
        (
            [RELEASE, _pub("v0.30.1", 35), _pub("v0.30.2", 22), _pub("v0.30.3", 4), _pub("v0.30.4", 1)],
            [{"number": 700, "found_in": None, "fixed_in": "0.30.3"}],
            "0.30.3",
            "blocking-bug-fixed-in-newer-pre-release",
        ),
        # A bug that starts after the chosen pre-release does not block it.
        (
            [RELEASE, _pub("v0.30.1", 35), _pub("v0.30.2", 22), _pub("v0.30.3", 4)],
            [{"number": 701, "found_in": "v0.30.3", "fixed_in": None}],
            "0.30.2",
            "time-rule",
        ),
        # A bug already fixed in the chosen pre-release does not block it.
        (
            [RELEASE, _pub("v0.30.1", 35), _pub("v0.30.2", 22)],
            [{"number": 702, "found_in": "v0.30.1", "fixed_in": "v0.30.2"}],
            "0.30.2",
            "time-rule",
        ),
        # Not fixed anywhere: nothing.
        (
            [RELEASE, _pub("v0.30.1", 35), _pub("v0.30.2", 22), _pub("v0.30.3", 4)],
            [{"number": 703, "found_in": "v0.30.1", "fixed_in": None}],
            None,
            "blocking-bug-not-fixed",
        ),
        # Fixed only in a version that is not published yet: nothing.
        (
            [RELEASE, _pub("v0.30.1", 35), _pub("v0.30.2", 22)],
            [{"number": 704, "found_in": "v0.30.2", "fixed_in": "v0.30.3"}],
            None,
            "blocking-bug-not-fixed",
        ),
        # The newer pre-release fixes one bug but carries another.
        (
            [RELEASE, _pub("v0.30.1", 35), _pub("v0.30.2", 22), _pub("v0.30.3", 4)],
            [
                {"number": 705, "found_in": "v0.30.2", "fixed_in": "v0.30.3"},
                {"number": 706, "found_in": "v0.30.3", "fixed_in": None},
            ],
            None,
            "blocking-bug-not-fixed",
        ),
    ],
)
def test_promotion_pick(publications, bugs, version, reason) -> None:
    result = pd.pick_promotion(publications, bugs, TODAY)
    assert result["version"] == version
    assert result["propose"] is (version is not None)
    assert result["reason"] == reason
    json.dumps(result)


def test_promotion_pick_reports_ages_and_blocking_bugs() -> None:
    publications = [RELEASE, _pub("v0.30.1", 35), _pub("v0.30.2", 22), _pub("v0.30.3", 4)]
    bugs = [{"number": 700, "found_in": "v0.30.2", "fixed_in": "v0.30.3"}]
    result = pd.pick_promotion(publications, bugs, TODAY)
    assert result["oldest_unpromoted"] == {"version": "0.30.1", "age_days": 35}
    assert result["age_days"] == 4
    assert result["blocked"] == [{"version": "0.30.2", "age_days": 22, "blocking_bugs": [700]}]


def test_promotion_pick_does_not_depend_on_input_order() -> None:
    publications = [_pub("v0.30.3", 19), _pub("v0.30.1", 35), RELEASE, _pub("v0.30.2", 20)]
    assert pd.pick_promotion(publications, [], TODAY)["version"] == "0.30.2"


@pytest.mark.parametrize(
    "publications",
    [
        [{"version": "v0.30.1", "kind": "beta", "published_at": "2026-10-01"}],
        [{"version": "nope", "kind": "pre-release", "published_at": "2026-10-01"}],
        [{"version": "v0.30.1", "kind": "pre-release", "published_at": "yesterday"}],
        [{"version": "v0.30.1", "kind": "pre-release"}],
    ],
)
def test_promotion_pick_rejects_malformed_publications(publications) -> None:
    with pytest.raises((ValueError, KeyError)):
        pd.pick_promotion(publications, [], TODAY)


# --- Retention (#634) ------------------------------------------------------------

FILES = ["CVMAnalytics-windows.zip", "CVMAnalytics-windows.zip.sha256"]


def _pre(n: int, *, assets: list[str] | None = None) -> dict:
    return {"version": f"v0.30.{n}", "kind": "pre-release", "assets": FILES if assets is None else assets}


def test_the_newest_ten_pre_releases_keep_their_files() -> None:
    plan = pd.pick_pruning([_pre(n) for n in range(1, 11)])
    assert plan == {"keep": 10, "kept": [f"v0.30.{n}" for n in range(10, 0, -1)], "prune": []}


def test_older_pre_releases_lose_their_files_newest_first_by_version_not_listing_order() -> None:
    listing = [_pre(n) for n in (3, 12, 1, 9, 2, 11, 10, 8, 7, 6, 5, 4)]
    plan = pd.pick_pruning(listing)
    assert plan["kept"] == [f"v0.30.{n}" for n in range(12, 2, -1)]
    assert plan["prune"] == [{"version": "v0.30.2", "assets": sorted(FILES)}, {"version": "v0.30.1", "assets": sorted(FILES)}]


def test_releases_are_never_pruned_and_do_not_count_toward_the_ten() -> None:
    releases = [{"version": "v0.29.2", "kind": "release", "assets": FILES}, {"version": "v0.30.0", "kind": "release", "assets": FILES}]
    plan = pd.pick_pruning(releases + [_pre(n) for n in range(1, 12)])
    assert plan["kept"] == [f"v0.30.{n}" for n in range(11, 1, -1)]
    assert [entry["version"] for entry in plan["prune"]] == ["v0.30.1"]


def test_legacy_rc_pre_releases_count_and_are_pruned_first() -> None:
    plan = pd.pick_pruning([{"version": "v0.30.0-rc.1", "kind": "pre-release", "assets": FILES}] + [_pre(n) for n in range(0, 10)])
    assert plan["kept"][-1] == "v0.30.0"
    assert plan["prune"] == [{"version": "v0.30.0-rc.1", "assets": sorted(FILES)}]


def test_a_pre_release_already_pruned_is_not_listed_again() -> None:
    plan = pd.pick_pruning([_pre(n, assets=[] if n == 1 else None) for n in range(1, 13)])
    assert [entry["version"] for entry in plan["prune"]] == ["v0.30.2"]


def test_pruning_rejects_an_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unknown publication kind"):
        pd.pick_pruning([{"version": "v0.30.1", "kind": "draft", "assets": []}])


# --- Command line --------------------------------------------------------------

def _run_cli(monkeypatch, capsys, command: str, payload: object) -> tuple[int, str, str]:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(raw), encoding="cp1252"))
    code = pd.main([command])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_cli_decide_prints_json(monkeypatch, capsys) -> None:
    payload = {
        "last_publication": "v0.30.0-rc.1",
        "prs": [{"number": 629, "class": "ships:pre", "title": "Publication workflow"}],
        "changed_paths": ["desktop/updater.py"],
    }
    code, out, _ = _run_cli(monkeypatch, capsys, "decide", payload)
    assert code == 0
    result = json.loads(out)
    assert result == pd.decide_publication(**payload)
    assert (result["publish"], result["kind"], result["version"], result["approval_required"]) == (
        True,
        "pre-release",
        "0.30.0",
        True,
    )


def test_cli_reads_utf8_whatever_the_console_encoding(monkeypatch, capsys, tmp_path) -> None:
    payload = {"last_publication": None, "prs": [{"number": 7, "class": "pre", "title": "Correção"}], "changed_paths": []}
    _, out, _ = _run_cli(monkeypatch, capsys, "decide", payload)
    assert json.loads(out)["reasons"]["prs"][0]["title"] == "Correção"

    source = tmp_path / "bom.json"  # Windows PowerShell writes a BOM
    source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8-sig")
    assert pd.main(["decide", "--input", str(source)]) == 0
    assert json.loads(capsys.readouterr().out)["reasons"]["prs"][0]["title"] == "Correção"


def test_cli_decide_reads_a_file(tmp_path, capsys) -> None:
    source = tmp_path / "input.json"
    source.write_text(json.dumps({"last_publication": None, "prs": [], "changed_paths": []}), encoding="utf-8")
    assert pd.main(["decide", "--input", str(source)]) == 0
    assert json.loads(capsys.readouterr().out)["publish"] is False


def test_cli_promote_prints_json(monkeypatch, capsys) -> None:
    payload = {"publications": [RELEASE, _pub("v0.30.1", 31)], "blocking_bugs": [], "today": TODAY}
    code, out, _ = _run_cli(monkeypatch, capsys, "promote", payload)
    assert code == 0
    assert json.loads(out)["version"] == "0.30.1"


@pytest.mark.parametrize(
    ("command", "payload"),
    [
        ("decide", {"prs": [], "changed_paths": []}),
        ("decide", {"last_publication": "garbage", "prs": [{"number": 1, "class": "pre"}], "changed_paths": []}),
        ("decide", ["not", "an", "object"]),
        ("promote", {"publications": [], "blocking_bugs": []}),
        ("prune", {"publications": [{"version": "v0.30.1", "kind": "pre-release"}]}),
    ],
)
def test_cli_rejects_invalid_input_without_a_decision(monkeypatch, capsys, command, payload) -> None:
    code, out, err = _run_cli(monkeypatch, capsys, command, payload)
    assert code == 2
    assert out == ""
    assert "invalid input" in err


def test_module_has_no_network_or_process_imports() -> None:
    import ast
    from pathlib import Path

    tree = ast.parse(Path(pd.__file__).read_text(encoding="utf-8"))
    imported = {
        name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for name in ([alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""])
    }
    assert imported == {"__future__", "argparse", "json", "re", "sys", "datetime", "fnmatch", "pathlib"}
