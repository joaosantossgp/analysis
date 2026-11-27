from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from desktop import dev_data


def _checkouts(tmp_path: Path) -> tuple[Path, Path]:
    main = tmp_path / "main"
    worktree = main / ".claude" / "worktrees" / "feature"
    worktree.mkdir(parents=True)
    return main, worktree


def _shared_database(main: Path) -> Path:
    """A WAL-mode shared dev database with one company row."""
    db_path = main / "data" / "dev-runtime" / "db" / "cvm_financials.db"
    db_path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE companies (name TEXT)")
        conn.execute("INSERT INTO companies VALUES ('PETROBRAS')")
        conn.commit()
    return db_path


def _companies(db_path: Path) -> list[tuple[str]]:
    with closing(sqlite3.connect(str(db_path))) as conn:
        return conn.execute("SELECT name FROM companies ORDER BY name").fetchall()


def _tree(root: Path) -> dict[str, int]:
    return {p.relative_to(root).as_posix(): p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}


def test_main_checkout_is_the_first_worktree_git_lists() -> None:
    porcelain = (
        "worktree C:/repo\nHEAD 3579045\nbranch refs/heads/main\n\n"
        "worktree C:/repo/.claude/worktrees/feature\nHEAD 6d83df4\nbranch refs/heads/feat/x\n"
    )

    assert dev_data.parse_main_checkout(porcelain) == Path("C:/repo")
    assert dev_data.parse_main_checkout("") is None


def test_main_checkout_falls_back_to_the_checkout_when_git_cannot_answer(tmp_path: Path) -> None:
    assert dev_data.main_checkout(tmp_path / "not-a-repo") == tmp_path / "not-a-repo"


def test_worktree_without_marker_uses_shared_dev_data(tmp_path: Path) -> None:
    main, worktree = _checkouts(tmp_path)

    resolved = dev_data.resolve(worktree, main=main)

    assert resolved.mode == dev_data.SHARED
    assert resolved.data_root == main / "data" / "dev-runtime"


def test_marker_switches_a_worktree_to_isolated_dev_data(tmp_path: Path) -> None:
    main, worktree = _checkouts(tmp_path)
    (worktree / dev_data.MARKER_NAME).write_text("isolated\n", encoding="utf-8")

    resolved = dev_data.resolve(worktree, main=main)

    assert resolved.mode == dev_data.ISOLATED
    assert resolved.data_root == worktree / "data" / "dev-runtime"
    assert resolved.shared_root == main / "data" / "dev-runtime"


def test_full_copy_marker_isolates_everything(tmp_path: Path) -> None:
    main, worktree = _checkouts(tmp_path)
    (worktree / dev_data.MARKER_NAME).write_text("full-copy\n", encoding="utf-8")

    resolved = dev_data.resolve(worktree, main=main)

    assert resolved.mode == dev_data.FULL_COPY
    assert resolved.data_root == worktree / "data" / "dev-runtime"


def test_main_checkout_always_owns_shared_dev_data(tmp_path: Path) -> None:
    main, _ = _checkouts(tmp_path)
    (main / dev_data.MARKER_NAME).write_text("isolated\n", encoding="utf-8")

    resolved = dev_data.resolve(main, main=main)

    assert resolved.mode == dev_data.SHARED
    assert resolved.data_root == main / "data" / "dev-runtime"


def test_isolate_copies_the_database_and_writes_the_marker(tmp_path: Path) -> None:
    main, worktree = _checkouts(tmp_path)
    shared_db = _shared_database(main)
    downloads = main / "data" / "dev-runtime" / "input" / "raw" / "dfp_cia_aberta_2024.zip"
    downloads.parent.mkdir(parents=True)
    downloads.write_bytes(b"zip")
    # A second connection holds rows that live only in the -wal sidecar.
    writer = sqlite3.connect(str(shared_db))
    writer.execute("INSERT INTO companies VALUES ('VALE')")
    writer.commit()
    before = _tree(main / "data")
    try:
        result = dev_data.isolate(worktree, main=main)
        after = _tree(main / "data")  # before the writer's own checkpoint on close
    finally:
        writer.close()

    own_root = worktree / "data" / "dev-runtime"
    assert result.mode == dev_data.ISOLATED
    assert _companies(own_root / "db" / "cvm_financials.db") == [("PETROBRAS",), ("VALE",)]
    assert not (own_root / "input").exists()  # downloads stay shared
    assert dev_data.resolve(worktree, main=main).mode == dev_data.ISOLATED
    assert after == before  # shared dev data is only read


def test_isolate_full_copy_also_copies_downloads_but_not_the_lock(tmp_path: Path) -> None:
    main, worktree = _checkouts(tmp_path)
    _shared_database(main)
    shared_root = main / "data" / "dev-runtime"
    (shared_root / "input" / "raw").mkdir(parents=True)
    (shared_root / "input" / "raw" / "dfp_cia_aberta_2024.zip").write_bytes(b"zip")
    (shared_root / "runtime.lock").write_text("{}", encoding="utf-8")

    result = dev_data.isolate(worktree, full_copy=True, main=main)

    own_root = worktree / "data" / "dev-runtime"
    assert result.mode == dev_data.FULL_COPY
    assert _companies(own_root / "db" / "cvm_financials.db") == [("PETROBRAS",)]
    assert (own_root / "input" / "raw" / "dfp_cia_aberta_2024.zip").read_bytes() == b"zip"
    assert not (own_root / "runtime.lock").exists()
    assert dev_data.resolve(worktree, main=main).mode == dev_data.FULL_COPY


def test_isolate_refuses_the_main_checkout(tmp_path: Path) -> None:
    main, _ = _checkouts(tmp_path)
    _shared_database(main)

    with pytest.raises(dev_data.IsolationError, match="main checkout"):
        dev_data.isolate(main, main=main)

    assert not (main / dev_data.MARKER_NAME).exists()


def test_isolate_keeps_an_existing_own_database_unless_forced(tmp_path: Path) -> None:
    main, worktree = _checkouts(tmp_path)
    _shared_database(main)
    own_db = worktree / "data" / "dev-runtime" / "db" / "cvm_financials.db"
    own_db.parent.mkdir(parents=True)
    with closing(sqlite3.connect(str(own_db))) as conn:
        conn.execute("CREATE TABLE companies (name TEXT)")
        conn.execute("INSERT INTO companies VALUES ('LOCAL')")
        conn.commit()

    with pytest.raises(dev_data.IsolationError, match="--force"):
        dev_data.isolate(worktree, main=main)
    assert _companies(own_db) == [("LOCAL",)]
    assert not (worktree / dev_data.MARKER_NAME).exists()

    dev_data.isolate(worktree, force=True, main=main)
    assert _companies(own_db) == [("PETROBRAS",)]


# --- Worktree list (#611) ------------------------------------------------------


def test_worktree_list_parsing_keeps_git_order_branches_and_removed_folders() -> None:
    porcelain = (
        "worktree C:/repo\nHEAD 3579045\nbranch refs/heads/main\n\n"
        "worktree C:/repo/.claude/worktrees/feature\nHEAD 6d83df4\nbranch refs/heads/feat/611-x\n"
        "locked claude agent (pid 16112)\n\n"
        "worktree C:/repo/.claude/worktrees/review\nHEAD 91c8249\ndetached\n\n"
        "worktree C:/temp/gone\nHEAD 4f1271f\nbranch refs/heads/old\nprunable gitdir file points to non-existent location\n"
    )

    assert dev_data.parse_worktrees(porcelain) == [
        {"path": Path("C:/repo"), "branch": "main", "prunable": False},
        {"path": Path("C:/repo/.claude/worktrees/feature"), "branch": "feat/611-x", "prunable": False},
        {"path": Path("C:/repo/.claude/worktrees/review"), "branch": None, "prunable": False},
        {"path": Path("C:/temp/gone"), "branch": "old", "prunable": True},
    ]
    assert dev_data.parse_worktrees("") == []


def _write_manifests(checkout: Path, requirements: str = "pywebview\n", lockfile: str = "{}\n") -> None:
    (checkout / "apps" / "desktop-web").mkdir(parents=True, exist_ok=True)
    (checkout / "requirements.txt").write_text(requirements, encoding="utf-8")
    (checkout / "apps" / "desktop-web" / "package-lock.json").write_text(lockfile, encoding="utf-8")


def test_worktree_list_flags_dependencies_and_isolated_data_and_drops_removed_worktrees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from desktop import dev_bootstrap

    main, feature = _checkouts(tmp_path)
    review = main / ".claude" / "worktrees" / "review"
    review.mkdir()
    for checkout in (main, feature, review):
        _write_manifests(checkout)
    _write_manifests(review, requirements="pywebview\nnew-package\n")
    dev_bootstrap.write_python_stamp(main, dev_bootstrap.python_stamp(main, "python"))
    dev_bootstrap.write_frontend_stamp(main)
    (feature / dev_data.MARKER_NAME).write_text("isolated\n", encoding="utf-8")
    porcelain = "".join(
        f"worktree {path.as_posix()}\nHEAD 1\nbranch refs/heads/{branch}\n\n"
        for path, branch in ((main, "main"), (feature, "feat/611"), (review, "review"), (tmp_path / "gone", "old"))
    )
    monkeypatch.setattr(dev_data, "_git_worktree_list", lambda _root: porcelain)

    listed = dev_data.list_worktrees(feature, env_root=main)

    assert [(w["name"], w["branch"], w["is_main_checkout"], w["isolated_data"]) for w in listed] == [
        ("main", "main", True, False),
        ("feature", "feat/611", False, True),
        ("review", "review", False, False),
    ], "a worktree whose folder is gone is not listed"
    assert [w["dependency_differences"] for w in listed] == [[], [], ["requirements.txt"]]
    assert listed[1]["path"] == str(feature)

    # The environment's own checkout never differs, even with a changed manifest.
    _write_manifests(main, lockfile='{"changed": true}\n')
    assert dev_data.list_worktrees(feature, env_root=main)[0]["dependency_differences"] == []
