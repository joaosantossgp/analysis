"""Regression for #657: a test run never resolves or touches the installed app's real data.

The root conftest.py points USERPROFILE, HOME and LOCALAPPDATA at a per-session temp
profile and fails the run when a test opens, creates or removes a file under the real
roots, which it captures from the environment pytest started with.
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path


def test_default_data_paths_resolve_outside_real_user_data(real_user_data) -> None:
    from desktop import app, updater
    from src.platform.settings import build_settings, get_settings

    resolved = [
        *(getattr(settings.paths, field.name) for settings in (build_settings(), get_settings()) for field in dataclasses.fields(settings.paths)),
        app._user_data_root(),
        app._legacy_localappdata_root(),
        updater._APPDATA_DIR,
        Path.home(),
    ]
    flat = [p for value in resolved for p in (value if isinstance(value, tuple) else (value,))]

    assert real_user_data.roots, "no real user-data root was captured; the guard would check nothing"
    assert [str(p) for p in flat if real_user_data.contains(p)] == []


def test_session_tripwire_records_touches_of_real_user_data(real_user_data) -> None:
    probe = Path(real_user_data.roots[0]) / "db" / "probe.db"
    before = len(real_user_data.touches)

    sys.audit("sqlite3.connect", str(probe))  # raises the audit event only: nothing is opened

    try:
        assert real_user_data.touches[before:] == [f"sqlite3.connect {probe}"]
    finally:
        del real_user_data.touches[before:]  # the probe must not fail the session
