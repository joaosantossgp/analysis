import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

# Ensure the project root is on sys.path so root-level modules can be imported in tests.
sys.path.insert(0, str(Path(__file__).resolve().parent))


# --- Keep every test run out of the installed app's real data (#657) -------------------
# Default data paths derive from USERPROFILE / HOME (Documents\CVMAnalytics) and
# LOCALAPPDATA (CVMAnalytics, updater state). This runs at conftest import, before test
# modules are collected, so import-time constants such as desktop.updater._APPDATA_DIR
# resolve to the temp profile too.


def _norm(path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _real_user_data_roots() -> tuple[str, ...]:
    roots = [Path(os.environ["USERPROFILE"]) / "Documents" / "CVMAnalytics"] if os.environ.get("USERPROFILE") else []
    try:
        roots.append(Path.home() / "Documents" / "CVMAnalytics")
    except RuntimeError:
        pass
    if os.environ.get("LOCALAPPDATA"):
        roots.append(Path(os.environ["LOCALAPPDATA"]) / "CVMAnalytics")
    return tuple(dict.fromkeys(_norm(root) for root in roots))


def is_real_user_data(path) -> bool:
    candidate = _norm(path)
    return any(candidate == root or candidate.startswith(root + os.sep) for root in REAL_USER_DATA_ROOTS)


REAL_USER_DATA_ROOTS = _real_user_data_roots()  # from the environment pytest started with
_ORIGINAL_ENV = dict(os.environ)
_TEST_PROFILE = Path(tempfile.mkdtemp(prefix="cvmanalytics-tests-"))

for _name in [n for n in os.environ if n.startswith(("CVM_", "CVMANALYTICS_")) or n in {"SQLITE_PATH", "DATABASE_URL", "HOMEDRIVE", "HOMEPATH"}]:
    del os.environ[_name]  # inherited data-path / database overrides of the developer's shell
os.environ["USERPROFILE"] = os.environ["HOME"] = str(_TEST_PROFILE / "profile")
os.environ["LOCALAPPDATA"] = str(_TEST_PROFILE / "localappdata")

# Tripwire: record any file a test opens, creates or removes under the real roots.
_TOUCH_EVENTS = {"open", "os.mkdir", "os.remove", "os.rename", "os.rmdir", "shutil.rmtree", "sqlite3.connect"}
_real_user_data_touches: list[str] = []


def _record_real_user_data_touch(event: str, args: tuple) -> None:
    if event in _TOUCH_EVENTS:
        for arg in args[:2]:
            try:
                if isinstance(arg, (str, os.PathLike)) and is_real_user_data(arg):
                    _real_user_data_touches.append(f"{event} {os.fspath(arg)}")
            except (TypeError, ValueError, OSError):  # bytes or invalid paths: never break the audited call
                pass


sys.addaudithook(_record_real_user_data_touch)


@pytest.fixture(scope="session", autouse=True)
def _fresh_settings_cache():
    from src.platform.settings import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def real_user_data():
    """The real installed-app data roots and the touches of them recorded this session."""
    return SimpleNamespace(roots=REAL_USER_DATA_ROOTS, contains=is_real_user_data, touches=_real_user_data_touches)


def pytest_sessionfinish(session):
    if _real_user_data_touches:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_sep("=", "tests touched the real installed-app data (#657)", red=True)
            for touch in sorted(set(_real_user_data_touches)):
                reporter.write_line(f"  {touch}", red=True)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_unconfigure(config):
    os.environ.clear()
    os.environ.update(_ORIGINAL_ENV)
    # shortcut: on Windows, SQLite files still held by cached engines survive this (~1 MB per run in %TEMP%); revisit if they pile up.
    shutil.rmtree(_TEST_PROFILE, ignore_errors=True)
