from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from desktop import dev_bootstrap as bootstrap


def _write_bootstrap_inputs(repo_root: Path) -> None:
    (repo_root / "requirements.txt").write_text("pywebview>=4.4\n", encoding="utf-8")
    frontend = repo_root / "apps" / "desktop-web"
    frontend.mkdir(parents=True)
    (frontend / "package-lock.json").write_text('{"lockfileVersion": 3}\n', encoding="utf-8")


def test_first_source_bootstrap_creates_venv_and_installs_declared_requirements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_bootstrap_inputs(tmp_path)
    commands: list[list[str]] = []
    python_path = bootstrap.venv_python(tmp_path)

    def fake_run(command: list[str], **_kwargs: object) -> None:
        commands.append(command)
        if command[1:3] == ["-m", "venv"]:
            python_path.parent.mkdir(parents=True)
            python_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(bootstrap, "_run_checked", fake_run)
    monkeypatch.setattr(bootstrap.sys, "executable", "C:/Python311/python.exe")

    assert bootstrap.ensure_source_environment([], repo_root=tmp_path) == []
    assert commands == [
        ["C:/Python311/python.exe", "-m", "venv", "--copies", str(tmp_path / ".venv")],
        [str(python_path), "-m", "pip", "install", "-r", str(tmp_path / "requirements.txt")],
    ]
    assert bootstrap.python_stamp_path(tmp_path).exists()


def test_unchanged_source_bootstrap_skips_pip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_bootstrap_inputs(tmp_path)
    monkeypatch.delenv("CVMANALYTICS_DEV_BOOTSTRAP_BASE_PYTHON", raising=False)
    python_path = bootstrap.venv_python(tmp_path)
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(bootstrap.sys, "executable", str(python_path))
    bootstrap.write_python_stamp(tmp_path, bootstrap.python_stamp(tmp_path, str(python_path)))
    monkeypatch.setattr(bootstrap, "_run_checked", lambda *_args, **_kwargs: pytest.fail("pip should not run"))

    assert bootstrap.ensure_source_environment([], repo_root=tmp_path) == []


def test_dev_frontend_runs_npm_ci_only_once_per_lockfile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_bootstrap_inputs(tmp_path)
    commands: list[list[str]] = []
    monkeypatch.setattr(bootstrap, "_run_checked", lambda command, **_: commands.append(command))
    monkeypatch.setattr(bootstrap, "_node_version", lambda: (22, 0, 0))

    bootstrap.ensure_dev_frontend(["--dev"], repo_root=tmp_path)
    bootstrap.ensure_dev_frontend(["--dev"], repo_root=tmp_path)

    assert commands == [["npm.cmd" if bootstrap._is_windows() else "npm", "ci"]]


def test_repair_flag_resynchronizes_frontend_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_bootstrap_inputs(tmp_path)
    commands: list[list[str]] = []
    monkeypatch.setattr(bootstrap, "_run_checked", lambda command, **_: commands.append(command))
    monkeypatch.setattr(bootstrap, "_node_version", lambda: (22, 0, 0))
    monkeypatch.setattr(bootstrap, "ensure_source_environment", lambda _argv, **_: ["--dev"])
    monkeypatch.setattr(bootstrap, "in_project_venv", lambda *_: True)
    bootstrap.write_frontend_stamp(tmp_path)

    bootstrap.bootstrap_and_reexec_if_needed(
        ["--dev", "--repair-dev-environment"], repo_root=tmp_path
    )

    assert commands == [["npm.cmd" if bootstrap._is_windows() else "npm", "ci"]]


def test_source_launcher_starts_project_venv_before_runtime_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_bootstrap_inputs(tmp_path)
    monkeypatch.setattr(bootstrap, "ensure_source_environment", lambda argv, **_: list(argv))
    monkeypatch.setattr(bootstrap, "ensure_dev_frontend", lambda argv, **_: None)
    monkeypatch.setattr(bootstrap, "in_project_venv", lambda *_: False)
    calls: list[list[str]] = []

    def fake_relaunch(command: list[str]) -> None:
        calls.append(command)
        raise SystemExit(0)

    monkeypatch.setattr(bootstrap, "_relaunch_in_venv", fake_relaunch)

    with pytest.raises(SystemExit) as exc:
        bootstrap.bootstrap_and_reexec_if_needed(["--dev"], repo_root=tmp_path)

    expected = str(bootstrap.venv_python(tmp_path))
    assert exc.value.code == 0
    assert calls == [[expected, "-m", "desktop.app", "--dev"]]


def test_failed_provisioning_names_command_and_repair_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_bootstrap_inputs(tmp_path)

    def fail(command: list[str], **_kwargs: object) -> None:
        raise bootstrap.BootstrapError(command, 1, "offline")

    monkeypatch.setattr(bootstrap, "_run_checked", fail)
    monkeypatch.setattr(bootstrap.sys, "executable", "C:/Python311/python.exe")

    with pytest.raises(bootstrap.BootstrapError, match="--repair-dev-environment"):
        bootstrap.ensure_source_environment([], repo_root=tmp_path)


def test_frozen_runtime_bypasses_development_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap.sys, "frozen", True, raising=False)
    assert bootstrap.bootstrap_and_reexec_if_needed(["--dev"]) == ["--dev"]


def test_root_manifest_declares_direct_numpy_runtime_dependency() -> None:
    requirements = Path("requirements.txt").read_text(encoding="utf-8")
    assert any(line.startswith("numpy") for line in requirements.splitlines())


# --- Running another worktree on an installed environment (#611) --------------


def _installed_environment(tmp_path: Path) -> tuple[Path, Path]:
    """An environment checkout with stamped `.venv` and `node_modules`, and a worktree with the same manifests."""
    env_root, worktree = tmp_path / "main", tmp_path / "worktree"
    for checkout in (env_root, worktree):
        checkout.mkdir()
        _write_bootstrap_inputs(checkout)
    bootstrap.write_python_stamp(env_root, bootstrap.python_stamp(env_root, "python"))
    package = env_root / "apps" / "desktop-web" / "node_modules" / "vite"
    (package / "bin").mkdir(parents=True)
    (package / "bin" / "vite.js").write_text("// vite\n", encoding="utf-8")
    (package.parent / ".vite" / "deps").mkdir(parents=True)
    (package.parent / ".vite" / "deps" / "react.js").write_text("// cache\n", encoding="utf-8")
    bootstrap.write_frontend_stamp(env_root)
    return env_root, worktree


def test_dependency_match_compares_manifests_with_the_installed_fingerprints(tmp_path: Path) -> None:
    env_root, worktree = _installed_environment(tmp_path)
    assert bootstrap.dependency_differences(env_root, worktree) == []

    (worktree / "requirements.txt").write_text("pywebview>=5\n", encoding="utf-8")
    assert bootstrap.dependency_differences(env_root, worktree) == ["requirements.txt"]

    (worktree / "apps" / "desktop-web" / "package-lock.json").unlink()
    assert bootstrap.dependency_differences(env_root, worktree) == [
        "requirements.txt",
        "apps/desktop-web/package-lock.json",
    ], "a missing manifest is a difference"


def test_dependency_match_needs_an_installed_environment(tmp_path: Path) -> None:
    env_root, worktree = _installed_environment(tmp_path)
    bootstrap.python_stamp_path(env_root).unlink()
    bootstrap.frontend_stamp_path(env_root).unlink()

    assert bootstrap.dependency_differences(env_root, worktree) == [
        "requirements.txt",
        "apps/desktop-web/package-lock.json",
    ]


def test_linked_frontend_dependencies_run_from_the_worktree_and_never_touch_the_source(tmp_path: Path) -> None:
    env_root, worktree = _installed_environment(tmp_path)
    source = env_root / "apps" / "desktop-web" / "node_modules"
    target = worktree / "apps" / "desktop-web" / "node_modules"

    bootstrap.link_frontend_dependencies(env_root, worktree)

    assert (target / "vite" / "bin" / "vite.js").read_text(encoding="utf-8") == "// vite\n"
    assert not (target / ".vite").exists(), "Vite's cache belongs to each checkout's own dev server"
    assert bootstrap.dependency_differences(worktree, worktree) == [
        "requirements.txt"
    ], "the worktree's node_modules now counts as installed for its lockfile"

    # npm ci in the worktree, or deleting the worktree, only removes its own names.
    shutil.rmtree(target)
    assert (source / "vite" / "bin" / "vite.js").read_text(encoding="utf-8") == "// vite\n"


def test_linking_frontend_dependencies_again_is_a_no_op(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_root, worktree = _installed_environment(tmp_path)
    bootstrap.link_frontend_dependencies(env_root, worktree)
    monkeypatch.setattr(bootstrap.shutil, "copytree", lambda *_a, **_k: pytest.fail("already installed"))

    bootstrap.link_frontend_dependencies(env_root, worktree)


def test_linking_frontend_dependencies_needs_installed_ones(tmp_path: Path) -> None:
    env_root, worktree = tmp_path / "main", tmp_path / "worktree"
    worktree.mkdir()
    _write_bootstrap_inputs(worktree)

    with pytest.raises(OSError, match="run dev mode from"):
        bootstrap.link_frontend_dependencies(env_root, worktree)


# --- A worktree's own environment, installed by a worktree switch (#612) -------

BOTH = [bootstrap.PYTHON_MANIFEST, bootstrap.FRONTEND_MANIFEST]


def _fake_installs(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Record install commands; creating a venv creates its interpreter."""
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> None:
        commands.append([str(part) for part in command])
        if command[1:3] == ["-m", "venv"]:
            python = bootstrap.venv_python(Path(command[-1]).parent)
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")

    monkeypatch.setattr(bootstrap, "_run_checked", fake_run)
    monkeypatch.setattr(bootstrap, "_node_version", lambda: (22, 0, 0))
    return commands


def test_pending_installs_reuse_the_worktree_s_own_bootstrap_stamps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env_root, worktree = _installed_environment(tmp_path)
    commands = _fake_installs(monkeypatch)
    assert bootstrap.pending_installs(worktree, BOTH) == BOTH, "nothing of its own is installed yet"

    bootstrap.provision(worktree, BOTH)
    assert bootstrap.pending_installs(worktree, BOTH) == [], "unchanged manifests: a second switch installs nothing"
    assert len(commands) == 3

    (worktree / "requirements.txt").write_text("pywebview>=5\n", encoding="utf-8")
    assert bootstrap.pending_installs(worktree, BOTH) == [bootstrap.PYTHON_MANIFEST]
    assert bootstrap.pending_installs(worktree, [bootstrap.FRONTEND_MANIFEST]) == [], "only the differing parts count"


def test_provision_installs_only_the_given_parts_and_reports_each_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env_root, worktree = _installed_environment(tmp_path)
    commands = _fake_installs(monkeypatch)
    steps: list[str] = []

    bootstrap.provision(worktree, [bootstrap.FRONTEND_MANIFEST], steps.append)
    assert commands == [["npm.cmd" if bootstrap._is_windows() else "npm", "ci"]]
    assert steps == ["Installing frontend packages"]

    bootstrap.provision(worktree, BOTH, steps.append)
    assert steps[1:] == ["Creating Python environment", "Installing Python packages"], "the frontend is current"
    assert commands[1][1:] == ["-m", "venv", "--copies", str(worktree / ".venv")]
    assert commands[2] == [
        str(bootstrap.venv_python(worktree)), "-m", "pip", "install", "-r", str(worktree / "requirements.txt")
    ]


def test_installing_over_linked_frontend_dependencies_never_touches_the_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_root, worktree = _installed_environment(tmp_path)
    bootstrap.link_frontend_dependencies(env_root, worktree)
    vite = Path("apps", "desktop-web", "node_modules", "vite", "bin", "vite.js")
    if os.stat(worktree / vite).st_nlink < 2:
        pytest.skip("hard links unsupported here: the worktree got copies")
    (worktree / "apps" / "desktop-web" / "package-lock.json").write_text('{"tiny": 1}\n', encoding="utf-8")
    source_before = {path: path.read_bytes() for path in (env_root / "apps").rglob("*") if path.is_file()}

    def npm_ci_writing_in_place(command: list[str], *, cwd: Path) -> None:
        (cwd / "node_modules" / "vite" / "bin").mkdir(parents=True, exist_ok=True)
        (cwd / "node_modules" / "vite" / "bin" / "vite.js").write_text("// vite 2\n", encoding="utf-8")

    monkeypatch.setattr(bootstrap, "_run_checked", npm_ci_writing_in_place)
    monkeypatch.setattr(bootstrap, "_node_version", lambda: (22, 0, 0))

    bootstrap.ensure_dev_frontend(["--dev"], repo_root=worktree)

    assert (worktree / vite).read_text(encoding="utf-8") == "// vite 2\n"
    assert {path: path.read_bytes() for path in (env_root / "apps").rglob("*") if path.is_file()} == source_before
    assert bootstrap.pending_installs(worktree, [bootstrap.FRONTEND_MANIFEST]) == []


def test_files_rewritten_in_place_are_copied_not_linked(tmp_path: Path) -> None:
    env_root, worktree = _installed_environment(tmp_path)
    hidden_lockfile = Path("apps", "desktop-web", "node_modules", ".package-lock.json")
    (env_root / hidden_lockfile).write_text('{"packages": {}}\n', encoding="utf-8")
    bootstrap.link_frontend_dependencies(env_root, worktree)
    vite = Path("apps", "desktop-web", "node_modules", "vite", "bin", "vite.js")
    if os.stat(worktree / vite).st_nlink < 2:
        pytest.skip("hard links unsupported here: the worktree got copies")

    # `npm install --package-lock-only` in the worktree rewrites npm's hidden lockfile in place.
    (worktree / hidden_lockfile).write_text('{"packages": {"is-number": {}}}\n', encoding="utf-8")
    (worktree / "apps" / "desktop-web" / "package-lock.json").write_text('{"tiny": 1}\n', encoding="utf-8")
    bootstrap.write_frontend_stamp(worktree)

    assert (env_root / hidden_lockfile).read_text(encoding="utf-8") == '{"packages": {}}\n'
    assert bootstrap.dependency_differences(env_root, env_root) == [], "env_root's stamp still matches its lockfile"


def test_linking_replaces_a_bootstrap_install_for_another_lockfile_instead_of_mixing(tmp_path: Path) -> None:
    env_root, worktree = _installed_environment(tmp_path)
    own = worktree / "apps" / "desktop-web" / "node_modules"
    (own / "left-over").mkdir(parents=True)
    (own / "left-over" / "index.js").write_text("// from its own older install\n", encoding="utf-8")
    bootstrap.frontend_stamp_path(worktree).write_text('{"lockfile_sha256": "older"}\n', encoding="utf-8")

    bootstrap.link_frontend_dependencies(env_root, worktree)

    assert not (own / "left-over").exists()
    assert (own / "vite" / "bin" / "vite.js").read_text(encoding="utf-8") == "// vite\n"


def test_linking_keeps_a_plain_npm_install_of_the_worktree(tmp_path: Path) -> None:
    env_root, worktree = _installed_environment(tmp_path)
    own = worktree / "apps" / "desktop-web" / "node_modules"
    (own / "vite" / "bin").mkdir(parents=True)
    (own / "vite" / "bin" / "vite.js").write_text("// its own npm ci, maybe in use\n", encoding="utf-8")

    bootstrap.link_frontend_dependencies(env_root, worktree)

    assert (own / "vite" / "bin" / "vite.js").read_text(encoding="utf-8") == "// its own npm ci, maybe in use\n"
    assert bootstrap.dependency_differences(worktree, worktree) == [bootstrap.PYTHON_MANIFEST]
