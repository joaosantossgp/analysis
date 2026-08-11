from __future__ import annotations

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
