# Phase 0 — User Data Safety

> [!NOTE]
> **Historical migration document.** Phase 0 user-data safety contract was implemented and validated through `v0.17.0`. The user-data root and updater contract described here remain accurate but are no longer an active migration plan. Current source of truth: `README.md`, `docs/reference/repository-map.md`.

## Purpose

Protect user data before any frontend/runtime migration.

## Files changed

- `desktop/app.py`
- `desktop/update_helper.ps1`
- `desktop/build_desktop.ps1`

## Runtime user data location

```text
%LOCALAPPDATA%\CVMAnalytics\
  db\
    cvm_financials.db
  output\
  logs\
  cache\
  backup\
  update_rollback\
  versions\
  recovery.log
```

## DB contract

- Active runtime DB lives at `%LOCALAPPDATA%\CVMAnalytics\db\cvm_financials.db`.
- Install-dir DB (`<exe-dir>/data/db/cvm_financials.db`) is legacy only.
- Existing LOCALAPPDATA DB must never be overwritten by the app or updater.
- Legacy install-dir DB is copied once using a WAL-safe SQLite Backup-API copy. WAL/SHM sidecars are also preserved as a forensic snapshot in `backup/legacy-db-<utc-ts>/` but the target DB is a clean self-contained snapshot.
- Fresh install (no target DB, no legacy DB) initializes a usable DB via `src.database.init_db_tables` before the bridge serves any request.
- Idempotency comes from target-existence: if the target DB exists, the migrator and initializer are no-ops on that file. No sentinel file is used — recovery scenarios are not blocked.
- Updates must never overwrite user DB, output, logs, or cache.

## Startup order (bundled mode only)

In `desktop/app.py::main`:

1. `_configure_bundled_data_paths()` — provisions LOCALAPPDATA subdirs and sets env vars (`SQLITE_PATH`, `CVM_DB_DIR`, `CVM_DATA_DIR`, `CVM_OUTPUT_DIR`, `CVM_LOG_DIR`, `CVM_CACHE_DIR`).
2. `_migrate_legacy_db_once()` — if target absent and legacy present, WAL-safe copy via `sqlite3.Connection.backup()` on a read-only URI handle.
3. `_ensure_db_initialized()` — idempotent `init_db_tables` on the target engine. Required for fresh installs.
4. `CVMBridge()` is instantiated.

Dev mode (`_bundled() == False`) is unchanged: paths resolved relative to repo root by `src/settings.py` defaults; migrator and initializer are no-ops.

## Update helper contract

The updater may overwrite only:

- `CVMAnalytics.exe`
- `_internal\` (recursively)

The updater must never touch:

- `data\`
- `output\`
- `logs\`
- `cache\`
- `tmp\`
- `backup\`
- `versions\`
- `update_rollback\`
- `*.db`, `*.db-wal`, `*.db-shm` anywhere

Pre-swap, the helper snapshots existing allowlisted entries into `%LOCALAPPDATA%\CVMAnalytics\update_rollback\<utc-ts>\` for manual recovery.

## Validation performed (sandbox)

- Dev-mode no-op: envs not mutated, migrator and initializer return.
- Bundled fresh install: LOCALAPPDATA subdirs provisioned; `init_db_tables` creates 7 tables on empty DB.
- Bundled legacy upgrade with uncheckpointed WAL (autocheckpoint disabled, open writer): all rows including the dirty-WAL row reach the target. Target has no stale `-wal` / `-shm` sidecars.
- Recovery: target deleted while legacy still present → re-migrates from legacy on next launch.
- Recovery: target + legacy both gone → `recovery.log` records the situation, downstream initializer creates fresh schema.
- Idempotency: target exists → migrator is a no-op, `recovery.log` not appended.
- Updater helper end-to-end against sandbox install: `data/`, `output/`, `logs/` preserved byte-for-byte; allowlisted entries swapped; rollback dir contains pre-swap state.
- PowerShell parse: both `update_helper.ps1` and `build_desktop.ps1` parse clean.
- Python import: `desktop.app` imports without error.

## Validation deferred (require packaged build)

- Full PyInstaller packaged smoke test.
- Real release ZIP layout verification against `update_helper.ps1` allowlist.
- Real update against a published GitHub release.
- Actual user-machine legacy upgrade.
- WebView2 launch smoke test under bundled mode.
- `_internal/web_standalone/` server launch with the new env layout.

## Required before release

Before shipping a public Phase 0 release:

1. Run `desktop/build_desktop.ps1`.
2. Fresh-install smoke: delete `%LOCALAPPDATA%\CVMAnalytics`, run the exe, confirm DB created in LOCALAPPDATA and app boots.
3. Legacy DB migration smoke: place a real DB under `<exe-dir>/data/db/`, delete `%LOCALAPPDATA%\CVMAnalytics`, run the exe, confirm migrated DB content and that legacy file is untouched.
4. Existing LOCALAPPDATA DB preservation smoke: start with a populated LOCALAPPDATA DB plus a different legacy DB; confirm LOCALAPPDATA DB content is unchanged.
5. Update helper smoke against the real release ZIP: confirm exe + `_internal/` swap, user-data dirs untouched, rollback dir populated.
