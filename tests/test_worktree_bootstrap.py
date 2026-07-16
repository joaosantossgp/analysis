from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = REPO_ROOT / "scripts" / "setup" / "bootstrap_worktree.ps1"
WORKTREE_CREATE = REPO_ROOT / "scripts" / "governance" / "worktree_create.ps1"


def test_worktree_bootstrap_restores_missing_local_vite(tmp_path: Path) -> None:
    fixture_root = tmp_path / "fixture"
    frontend = fixture_root / "apps" / "desktop-web"
    frontend.mkdir(parents=True)
    (frontend / "package.json").write_text("{}\n", encoding="utf-8")
    (frontend / "package-lock.json").write_text("{}\n", encoding="utf-8")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    npm_log = tmp_path / "npm.log"
    _write_command(
        fake_bin / "node.cmd",
        "@echo v22.0.0\r\n",
    )
    _write_command(
        fake_bin / "python.cmd",
        "@echo Python 3.11.0\r\n",
    )
    _write_command(
        fake_bin / "npm.cmd",
        "@echo %CD% ^| %*>> \"%NPM_LOG%\"\r\n"
        "@if \"%~1\"==\"ci\" (\r\n"
        "  @mkdir \"%CD%\\node_modules\\.bin\" 2>nul\r\n"
        "  @echo @echo vite 6.0.0> \"%CD%\\node_modules\\.bin\\vite.cmd\"\r\n"
        ")\r\n",
    )

    env = os.environ | {
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "NPM_LOG": str(npm_log),
    }
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(BOOTSTRAP),
            "-RepoRoot",
            str(fixture_root),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert f"Worktree: {fixture_root}" in result.stdout
    assert "Frontend dependencies are missing; running npm ci." in result.stdout
    assert (frontend / "node_modules" / ".bin" / "vite.cmd").is_file()
    assert "ci" in npm_log.read_text(encoding="utf-8")


def test_worktree_creator_defaults_to_main() -> None:
    source = WORKTREE_CREATE.read_text(encoding="utf-8")

    assert '[string]$Base = "main"' in source


def _write_command(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
