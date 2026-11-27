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
