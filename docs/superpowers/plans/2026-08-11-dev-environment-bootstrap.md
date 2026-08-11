# Development Environment Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the normal source desktop command create and use an isolated, synchronized development environment without manual package installs.

**Architecture:** A standard-library-only bootstrap runs at the top of `desktop.app` before third-party imports.  It creates and synchronizes `.venv` from the root requirements manifest, installs the locked Vite dependency tree when `--dev` needs it, and then re-executes the desktop module through `.venv`.  Frozen PyInstaller execution bypasses this flow.

**Tech Stack:** Python 3.11+, `venv`, `subprocess`, `hashlib`, pytest, PowerShell, Node.js 22+, npm, Vite, PyInstaller.

## Global Constraints

- Do not dynamically install packages based on `ImportError`.
- Root `requirements.txt` is the canonical desktop/core Python manifest.
- Use `npm ci` with `apps/desktop-web/package-lock.json` for frontend synchronization.
- Keep frozen/PyInstaller startup behavior unchanged.
- Python 3.11+ and Node.js 22+ are explicit development prerequisites.
- Do not modify inactive Next.js architecture or production packaging without evidence.

---

### Task 1: Isolated Python bootstrap

**Files:**
- Create: `desktop/dev_bootstrap.py`
- Create: `tests/test_dev_bootstrap.py`

**Interfaces:**
- Produces: `ensure_source_environment(argv: Sequence[str]) -> list[str]`.
- Produces: `BootstrapError(RuntimeError)` with actionable failure text.
- Produces: `reexec_in_venv(argv: Sequence[str]) -> None`.

- [ ] **Step 1: Write failing tests for a new environment and unchanged manifest**

```python
def test_ensure_source_environment_creates_venv_and_installs_declared_requirements(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(bootstrap, "_run_checked", lambda command, **_: commands.append(command))
    bootstrap.ensure_source_environment(["--dev"], repo_root=tmp_path)
    assert commands[0][-3:] == ["-m", "venv", str(tmp_path / ".venv")]
    assert commands[1][-4:] == ["-m", "pip", "install", "-r", str(tmp_path / "requirements.txt")]

def test_ensure_source_environment_skips_pip_when_manifest_stamp_matches(tmp_path, monkeypatch):
    bootstrap.write_python_stamp(tmp_path, bootstrap.python_stamp(tmp_path, sys.executable))
    monkeypatch.setattr(bootstrap, "_run_checked", pytest.fail)
    assert bootstrap.ensure_source_environment([], repo_root=tmp_path) == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_dev_bootstrap.py -q`

Expected: FAIL because `desktop.dev_bootstrap` does not exist.

- [ ] **Step 3: Implement standard-library-only environment provisioning**

```python
def ensure_source_environment(argv: Sequence[str], *, repo_root: Path | None = None) -> list[str]:
    root = repo_root or repository_root()
    validate_python_version()
    if rebuild_requested(argv):
        remove_venv(root / ".venv")
    if stamp_matches(root, sys.executable, repair=repair_requested(argv)):
        return strip_bootstrap_flags(argv)
    create_venv_if_missing(root, sys.executable)
    install_requirements(root)
    write_python_stamp(root, python_stamp(root, sys.executable))
    return strip_bootstrap_flags(argv)
```

Use `subprocess.run(..., check=False, capture_output=True, text=True)` through
`_run_checked`, and raise `BootstrapError` that includes the command, exit code,
and output when creation or installation fails.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `pytest tests/test_dev_bootstrap.py -q`

Expected: PASS.

### Task 2: Vite dependency bootstrap and re-execution boundary

**Files:**
- Modify: `desktop/dev_bootstrap.py`
- Modify: `tests/test_dev_bootstrap.py`
- Modify: `desktop/app.py:25-43`

**Interfaces:**
- Consumes: `ensure_source_environment(argv)` and `BootstrapError` from Task 1.
- Produces: `ensure_dev_frontend(argv, repo_root=...) -> None`.
- Produces: `bootstrap_and_reexec_if_needed(argv: Sequence[str]) -> list[str]`.

- [ ] **Step 1: Write failing tests for Vite synchronization and re-execution**

```python
def test_ensure_dev_frontend_runs_npm_ci_only_when_lockfile_changes(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(bootstrap, "_run_checked", lambda command, **_: commands.append(command))
    bootstrap.ensure_dev_frontend(["--dev"], repo_root=tmp_path)
    assert commands == [["npm.cmd", "ci"]]
    bootstrap.write_frontend_stamp(tmp_path)
    bootstrap.ensure_dev_frontend(["--dev"], repo_root=tmp_path)
    assert commands == [["npm.cmd", "ci"]]

def test_bootstrap_reexecs_with_project_venv_before_runtime_imports(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "ensure_source_environment", lambda argv, **_: list(argv))
    monkeypatch.setattr(bootstrap, "ensure_dev_frontend", lambda argv, **_: None)
    monkeypatch.setattr(bootstrap, "in_project_venv", lambda *_: False)
    with pytest.raises(bootstrap.ReexecRequested) as exc:
        bootstrap.bootstrap_and_reexec_if_needed(["--dev"], repo_root=tmp_path)
    assert exc.value.command[-4:] == ["-m", "desktop.app", "--dev"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_dev_bootstrap.py -q`

Expected: FAIL because the frontend and re-execution APIs do not exist.

- [ ] **Step 3: Implement frontend synchronization and source re-execution**

```python
def bootstrap_and_reexec_if_needed(argv: Sequence[str]) -> list[str]:
    if is_frozen():
        return list(argv)
    clean_argv = ensure_source_environment(argv)
    ensure_dev_frontend(clean_argv)
    if not in_project_venv(repository_root(), sys.executable):
        raise ReexecRequested([str(venv_python(repository_root())), "-m", "desktop.app", *clean_argv])
    return clean_argv
```

At the top of `desktop/app.py`, call this function before `import webview` and
`from desktop.bridge import CVMBridge`; handle `ReexecRequested` with
`os.execv` so the process is replaced rather than duplicated.  Do not run this
path when `sys.frozen` is true.

- [ ] **Step 4: Run focused regression tests**

Run: `pytest tests/test_dev_bootstrap.py tests/test_desktop_runtime_paths.py -q`

Expected: PASS.

### Task 3: Dependency declaration and developer documentation

**Files:**
- Modify: `requirements.txt`
- Modify: `README.md`
- Modify: `docs/development.md`
- Modify: `docs/COMO_RODAR.md`
- Modify: `docs/troubleshooting.md`

**Interfaces:**
- Consumes: flags `--repair-dev-environment` and `--rebuild-dev-environment`.
- Documents: `python -m desktop.app --dev` as the single normal desktop dev command.

- [ ] **Step 1: Write a failing manifest-audit test**

```python
def test_root_manifest_declares_direct_numpy_runtime_dependency():
    requirements = Path("requirements.txt").read_text(encoding="utf-8")
    assert any(line.startswith("numpy") for line in requirements.splitlines())
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_dev_bootstrap.py::test_root_manifest_declares_direct_numpy_runtime_dependency -q`

Expected: FAIL because numpy is only transitively installed through pandas.

- [ ] **Step 3: Declare the direct dependency and update canonical docs**

Add `numpy>=1.24` to the root manifest.  Replace manual `.venv` creation and
`pip install` as the normal path with the single command, state Python 3.11+
and Node.js 22+ prerequisites, document `.venv`, both repair flags, first-run
network behavior, and the fact that packaged users do not install Python/pip.

- [ ] **Step 4: Run the manifest test**

Run: `pytest tests/test_dev_bootstrap.py::test_root_manifest_declares_direct_numpy_runtime_dependency -q`

Expected: PASS.

### Task 4: Fresh-environment and package verification

**Files:**
- Modify: `tests/test_dev_bootstrap.py`
- Inspect: `desktop/app.spec`, `desktop/build_desktop.ps1`, `.github/workflows/release-desktop.yml`

**Interfaces:**
- Verifies: source bootstrap invokes only declared manifests and frozen builds bypass it.

- [ ] **Step 1: Add failure-message and frozen-bypass tests**

```python
def test_failed_pip_install_names_command_exit_code_and_repair_action(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "_run_checked", lambda *_, **__: (_ for _ in ()).throw(bootstrap.BootstrapError("...")))
    with pytest.raises(bootstrap.BootstrapError, match="--repair-dev-environment"):
        bootstrap.ensure_source_environment([], repo_root=tmp_path)

def test_frozen_runtime_bypasses_bootstrap(monkeypatch):
    monkeypatch.setattr(bootstrap.sys, "frozen", True, raising=False)
    assert bootstrap.bootstrap_and_reexec_if_needed(["--dev"]) == ["--dev"]
```

- [ ] **Step 2: Run the test to verify it fails before the final implementation is present**

Run: `pytest tests/test_dev_bootstrap.py -q`

Expected: FAIL until error details and frozen bypass are implemented.

- [ ] **Step 3: Implement the minimal error and frozen behavior**

Ensure all bootstrap failures name the failed executable/arguments, exit code,
captured output, and `python -m desktop.app --repair-dev-environment --dev`.
Ensure `sys.frozen` returns arguments without creating `.venv`, running pip, or
requiring Node.

- [ ] **Step 4: Run full verification**

Run: `pytest tests/test_dev_bootstrap.py tests/test_desktop_runtime_paths.py -q`
Run: `python -m py_compile desktop/app.py desktop/dev_bootstrap.py desktop/bridge.py`
Run: `pytest tests -q`
Run: `npm --prefix apps/desktop-web run typecheck`
Run: `npm --prefix apps/desktop-web run test`
Run: `npm --prefix apps/desktop-web run build`

Expected: all applicable commands pass.  If Python or Node is absent in the
current environment, record the missing prerequisite and run the tests after
the bootstrap creates the isolated environment.

- [ ] **Step 5: Validate fresh and packaged paths**

Run the normal command from a temporary fresh checkout or after moving only
the project `.venv` aside: `python -m desktop.app --dev`.  Confirm it creates
`.venv`, installs declared dependencies, resolves `import webview`, and does
not rerun pip/npm on a second start.  Run `desktop/build_desktop.ps1` if Node
and the bootstrapped Python environment are available; inspect the resulting
`dist/CVMAnalytics/_internal` contents for bundled Python modules.  Do not
claim a clean-machine packaged launch without an actual clean Windows test.
