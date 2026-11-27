"""Dev data actions on real temp folders: move to backup, restore, delete (dev panel, #614)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from desktop import dev_data_actions as actions
from desktop.dev_data import FULL_COPY, ISOLATED, SHARED, DevData


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def read_tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def repo(tmp_path: Path) -> dict[str, Path]:
    """A main checkout with shared dev data and a worktree, both git checkouts."""
    main, worktree = tmp_path / "main", tmp_path / "wt-614"
    (main / ".git").mkdir(parents=True)
    write(worktree / ".git", "gitdir: ../main/.git/worktrees/wt-614\n")
    shared = main / "data" / "dev-runtime"
    write(shared / "db" / "cvm_financials.db", "shared db v1")
    write(shared / "input" / "raw" / "dfp_2024.zip", "zip bytes")
    write(shared / "cache" / "universe.json", "{}")
    return {"main": main, "worktree": worktree, "shared": shared, "own": worktree / "data" / "dev-runtime"}


@pytest.fixture
def environ(tmp_path: Path) -> dict[str, str]:
    return {"USERPROFILE": str(tmp_path / "profile")}


def shared_dev(repo: dict[str, Path]) -> DevData:
    return DevData(SHARED, repo["shared"], repo["shared"])


def request(dev: DevData, operation: str, target: str) -> dict[str, str]:
    return {"operation": operation, "target": target, "mode": dev.mode,
            "data_root": str(dev.data_root), "shared_root": str(dev.shared_root)}


def leftovers(backups: Path) -> list[str]:
    return [p.name for p in backups.iterdir() if p.name.startswith(".trash-")] if backups.exists() else []


# --- describe -----------------------------------------------------------------


def test_describe_lists_the_three_targets_of_shared_dev_data_with_sizes(repo: dict[str, Path]) -> None:
    described = {item["target"]: item for item in actions.describe(shared_dev(repo))}

    assert list(described) == ["db", "input", "all"]
    assert described["db"] == {
        "target": "db",
        "path": str(repo["shared"] / "db"),
        "exists": True,
        "size_bytes": len("shared db v1"),
        "shared": True,
        "backup_path": str(repo["main"] / "data" / "dev-runtime.backup" / "db"),
        "backup_exists": False,
        "backup_size_bytes": None,
    }
    assert described["input"]["size_bytes"] == len("zip bytes")
    assert described["all"]["path"] == str(repo["shared"])
    assert described["all"]["size_bytes"] == len("shared db v1") + len("zip bytes") + len("{}")
    assert all(item["shared"] for item in described.values())


def test_isolated_dev_data_resets_its_own_database_and_the_shared_downloads(repo: dict[str, Path]) -> None:
    write(repo["own"] / "db" / "cvm_financials.db", "own db")
    dev = DevData(ISOLATED, repo["own"], repo["shared"])

    described = {item["target"]: item for item in actions.describe(dev)}

    assert (described["db"]["path"], described["db"]["shared"]) == (str(repo["own"] / "db"), False)
    assert (described["input"]["path"], described["input"]["shared"]) == (str(repo["shared"] / "input"), True)
    assert described["input"]["backup_path"] == str(repo["main"] / "data" / "dev-runtime.backup" / "input")
    assert (described["all"]["path"], described["all"]["shared"]) == (str(repo["own"]), False)


def test_full_copy_dev_data_owns_every_target(repo: dict[str, Path]) -> None:
    dev = DevData(FULL_COPY, repo["own"], repo["shared"])

    described = actions.describe(dev)

    assert [item["path"] for item in described] == [str(repo["own"] / "db"), str(repo["own"] / "input"), str(repo["own"])]
    assert not any(item["shared"] for item in described)
    assert [item["exists"] for item in described] == [False, False, False]


# --- move to backup, restore, delete ------------------------------------------


def test_move_to_backup_keeps_only_the_latest_backup(repo: dict[str, Path], environ: dict[str, str]) -> None:
    dev = shared_dev(repo)
    backups = repo["main"] / "data" / "dev-runtime.backup"

    first = actions.perform(request(dev, "backup", "db"), environ)
    assert first["ok"] is True, first["message"]
    assert not (repo["shared"] / "db").exists()
    assert read_tree(backups / "db") == {"cvm_financials.db": "shared db v1"}

    write(repo["shared"] / "db" / "cvm_financials.db", "shared db v2")
    second = actions.perform(request(dev, "backup", "db"), environ)

    assert second == {"operation": "backup", "target": "db", "ok": True,
                      "message": f"Moved Database to backup ({repo['shared'] / 'db'})."}
    assert read_tree(backups / "db") == {"cvm_financials.db": "shared db v2"}, "the older backup is deleted"
    assert leftovers(backups) == []
    assert read_tree(repo["shared"] / "input") == {"raw/dfp_2024.zip": "zip bytes"}, "other targets are untouched"


def test_restore_replaces_current_data_with_the_backup(repo: dict[str, Path], environ: dict[str, str]) -> None:
    dev = shared_dev(repo)
    assert actions.perform(request(dev, "backup", "db"), environ)["ok"]
    write(repo["shared"] / "db" / "cvm_financials.db", "fresh first-run db")

    result = actions.perform(request(dev, "restore", "db"), environ)

    assert result["ok"] is True, result["message"]
    assert result["message"] == f"Restored the Database backup ({repo['shared'] / 'db'})."
    assert read_tree(repo["shared"] / "db") == {"cvm_financials.db": "shared db v1"}
    backups = repo["main"] / "data" / "dev-runtime.backup"
    assert not (backups / "db").exists(), "the backup became current data"
    assert leftovers(backups) == [], "the replaced data is removed"


def test_delete_removes_current_data_and_keeps_the_backup(repo: dict[str, Path], environ: dict[str, str]) -> None:
    dev = shared_dev(repo)
    assert actions.perform(request(dev, "backup", "input"), environ)["ok"]
    write(repo["shared"] / "input" / "raw" / "itr_2025.zip", "newer zip")

    result = actions.perform(request(dev, "delete", "input"), environ)

    assert result["ok"] is True, result["message"]
    assert not (repo["shared"] / "input").exists()
    backups = repo["main"] / "data" / "dev-runtime.backup"
    assert read_tree(backups / "input") == {"raw/dfp_2024.zip": "zip bytes"}
    assert leftovers(backups) == []


def test_everything_moves_the_whole_data_root_next_to_it_and_back(repo: dict[str, Path], environ: dict[str, str]) -> None:
    dev = shared_dev(repo)
    before = read_tree(repo["shared"])

    assert actions.perform(request(dev, "backup", "all"), environ)["ok"]
    assert not repo["shared"].exists()
    assert read_tree(repo["main"] / "data" / "dev-runtime.backup" / "all") == before

    write(repo["shared"] / "db" / "cvm_financials.db", "first-run db")  # the app started again
    assert actions.perform(request(dev, "restore", "all"), environ)["ok"]
    assert read_tree(repo["shared"]) == before


def test_isolated_downloads_target_backs_up_the_shared_folder(repo: dict[str, Path], environ: dict[str, str]) -> None:
    write(repo["own"] / "db" / "cvm_financials.db", "own db")
    dev = DevData(ISOLATED, repo["own"], repo["shared"])

    assert actions.perform(request(dev, "backup", "input"), environ)["ok"]

    assert not (repo["shared"] / "input").exists()
    assert (repo["main"] / "data" / "dev-runtime.backup" / "input" / "raw" / "dfp_2024.zip").exists()
    assert read_tree(repo["own"]) == {"db/cvm_financials.db": "own db"}


# --- failures leave data as it was --------------------------------------------


@pytest.fixture
def failing_rename(monkeypatch: pytest.MonkeyPatch):
    """Make renames out of one source path fail, as a locked file does on Windows."""
    real_rename = os.rename
    blocked: list[Path] = []

    def rename(source: str | Path, destination: str | Path) -> None:
        if Path(source) in blocked:
            raise PermissionError(13, "The process cannot access the file", str(source))
        real_rename(source, destination)

    monkeypatch.setattr(actions.os, "rename", rename)
    monkeypatch.setattr(actions.time, "sleep", lambda _seconds: None)
    return blocked


def test_failed_move_puts_the_older_backup_back(repo: dict[str, Path], environ: dict[str, str], failing_rename: list[Path]) -> None:
    dev = shared_dev(repo)
    assert actions.perform(request(dev, "backup", "db"), environ)["ok"]
    write(repo["shared"] / "db" / "cvm_financials.db", "shared db v2")
    failing_rename.append(repo["shared"] / "db")

    result = actions.perform(request(dev, "backup", "db"), environ)

    assert result["ok"] is False
    assert "PermissionError" in result["message"] or "cannot access" in result["message"]
    assert "Nothing was changed." in result["message"]
    backups = repo["main"] / "data" / "dev-runtime.backup"
    assert read_tree(repo["shared"] / "db") == {"cvm_financials.db": "shared db v2"}
    assert read_tree(backups / "db") == {"cvm_financials.db": "shared db v1"}, "the older backup is back in its slot"
    assert leftovers(backups) == []


def test_failed_restore_puts_current_data_back(repo: dict[str, Path], environ: dict[str, str], failing_rename: list[Path]) -> None:
    dev = shared_dev(repo)
    assert actions.perform(request(dev, "backup", "db"), environ)["ok"]
    write(repo["shared"] / "db" / "cvm_financials.db", "fresh first-run db")
    backups = repo["main"] / "data" / "dev-runtime.backup"
    failing_rename.append(backups / "db")

    result = actions.perform(request(dev, "restore", "db"), environ)

    assert result["ok"] is False
    assert "Nothing was changed." in result["message"]
    assert read_tree(repo["shared"] / "db") == {"cvm_financials.db": "fresh first-run db"}
    assert read_tree(backups / "db") == {"cvm_financials.db": "shared db v1"}
    assert leftovers(backups) == []


def test_failed_delete_changes_nothing(repo: dict[str, Path], environ: dict[str, str], failing_rename: list[Path]) -> None:
    failing_rename.append(repo["shared"] / "db")

    result = actions.perform(request(shared_dev(repo), "delete", "db"), environ)

    assert result["ok"] is False
    assert "Nothing was changed." in result["message"]
    assert read_tree(repo["shared"] / "db") == {"cvm_financials.db": "shared db v1"}


def test_a_rollback_that_fails_too_says_where_the_data_is(
    repo: dict[str, Path], environ: dict[str, str], failing_rename: list[Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    dev = shared_dev(repo)
    assert actions.perform(request(dev, "backup", "db"), environ)["ok"]
    write(repo["shared"] / "db" / "cvm_financials.db", "shared db v2")
    failing_rename.append(repo["shared"] / "db")
    backups = repo["main"] / "data" / "dev-runtime.backup"
    real_put_back = actions._put_back

    def put_back_blocked(moved: Path, original: Path, error: OSError, what: str) -> actions.ActionError:
        failing_rename.append(moved)
        return real_put_back(moved, original, error, what)

    monkeypatch.setattr(actions, "_put_back", put_back_blocked)
    result = actions.perform(request(dev, "backup", "db"), environ)

    assert result["ok"] is False
    [trash] = leftovers(backups)
    assert str(backups / trash) in result["message"]
    assert "by hand" in result["message"]
    assert read_tree(backups / trash) == {"cvm_financials.db": "shared db v1"}, "no data was lost"


def test_a_leftover_that_cannot_be_removed_is_a_warning(
    repo: dict[str, Path], environ: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def rmtree_fails(path: Path) -> None:
        raise PermissionError(13, "Access is denied", str(path))

    monkeypatch.setattr(actions.shutil, "rmtree", rmtree_fails)

    result = actions.perform(request(shared_dev(repo), "delete", "db"), environ)

    assert result["ok"] is True, "the data is out of the app's way"
    assert "delete it by hand" in result["message"]
    assert not (repo["shared"] / "db").exists()


# --- refusals: installed-app data, custom data, outside a checkout, in use ----


def test_installed_app_data_is_refused_and_never_touched(tmp_path: Path, environ: dict[str, str]) -> None:
    documents = Path(environ["USERPROFILE"]) / "Documents" / "CVMAnalytics"
    write(documents / "db" / "cvm_financials.db", "real user data")
    dev = DevData(SHARED, documents, documents)

    for operation in actions.OPERATIONS:
        result = actions.perform({**request(dev, operation, "db"), "confirm": "db"}, environ)
        assert result["ok"] is False
    assert read_tree(documents) == {"db/cvm_financials.db": "real user data"}
    assert "installed-app data" in actions.refusal(dev, environ)


def test_a_dev_data_folder_inside_installed_app_data_is_refused(tmp_path: Path, environ: dict[str, str]) -> None:
    checkout = Path(environ["USERPROFILE"]) / "Documents" / "CVMAnalytics" / "checkout"
    (checkout / ".git").mkdir(parents=True)
    root = checkout / "data" / "dev-runtime"

    assert "installed-app data" in actions.refusal(DevData(SHARED, root, root), environ)


def test_release_data_mode_and_a_custom_data_directory_are_refused(repo: dict[str, Path], environ: dict[str, str]) -> None:
    dev = shared_dev(repo)
    assert actions.refusal(dev, environ) is None

    assert "CVMANALYTICS_USE_RELEASE_DATA" in actions.refusal(dev, {**environ, "CVMANALYTICS_USE_RELEASE_DATA": "1"})
    custom = {**environ, "CVM_DATA_DIR": str(repo["worktree"] / "throwaway")}
    assert "CVM_DATA_DIR" in actions.refusal(dev, custom)
    assert actions.refusal(dev, {**environ, "CVM_DATA_DIR": str(repo["shared"])}) is None, "the launcher's own value"


def test_a_folder_that_is_not_dev_data_of_a_git_checkout_is_refused(tmp_path: Path, environ: dict[str, str]) -> None:
    elsewhere = tmp_path / "elsewhere" / "data" / "dev-runtime"
    write(elsewhere / "db" / "x.db", "x")
    not_dev_runtime = tmp_path / "main"
    (not_dev_runtime / ".git").mkdir(parents=True)

    for root in (elsewhere, not_dev_runtime):
        dev = DevData(SHARED, root, root)
        assert "not the dev data folder of a git checkout" in actions.refusal(dev, environ)
        assert actions.perform(request(dev, "delete", "db"), environ)["ok"] is False
    assert (elsewhere / "db" / "x.db").exists()


def test_shared_mode_must_point_at_the_shared_root(repo: dict[str, Path], environ: dict[str, str]) -> None:
    write(repo["worktree"] / ".git", "gitdir: x\n")
    assert actions.refusal(DevData(SHARED, repo["own"], repo["shared"]), environ) is not None
    assert actions.refusal(DevData("custom", repo["shared"], repo["shared"]), environ) is not None


def test_data_held_by_another_running_app_is_refused(repo: dict[str, Path], environ: dict[str, str]) -> None:
    write(repo["shared"] / "runtime.lock", json.dumps({"pid": os.getppid()}))  # a live process that is not us
    dev = shared_dev(repo)

    result = actions.perform(request(dev, "backup", "db"), environ)

    assert result["ok"] is False
    assert f"in use by another CVMAnalytics process (PID {os.getppid()})" in result["message"]
    assert (repo["shared"] / "db" / "cvm_financials.db").exists()
    assert actions.check(dev, "backup", "db", own_pid=os.getppid()) is None, "the app's own lock does not count"


def test_check_says_when_there_is_nothing_to_act_on(repo: dict[str, Path]) -> None:
    dev = DevData(FULL_COPY, repo["own"], repo["shared"])
    pid = os.getpid()

    assert "nothing to move" in actions.check(dev, "backup", "db", own_pid=pid)
    assert "nothing to delete" in actions.check(dev, "delete", "all", own_pid=pid)
    assert "no Database backup" in actions.check(dev, "restore", "db", own_pid=pid)
    assert "Unknown data target" in actions.check(dev, "backup", "logs", own_pid=pid)
    assert "Unknown data action" in actions.check(dev, "wipe", "db", own_pid=pid)


def test_a_malformed_request_fails_plainly(environ: dict[str, str]) -> None:
    result = actions.perform({"operation": "delete", "target": "db"}, environ)

    assert result["ok"] is False
    assert "KeyError" in result["message"]
