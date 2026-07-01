# Release Process

This file is a short pointer for release-specific work. The canonical build,
packaging, updater, and validation contract is
[`build-release.md`](build-release.md).

## Release Artifact

A release is the packaged Windows desktop app distributed through GitHub
Releases:

```text
CVMAnalytics-windows-v<version>.zip
CVMAnalytics-windows-v<version>.zip.sha256
CVMAnalytics-windows.zip
CVMAnalytics-windows.zip.sha256
```

The ZIP root must be flat: `CVMAnalytics.exe` and `_internal/` at the archive
root.

## When To Release

Cut a release when installed users need the change:

- Python core or bridge behavior that changes shipped functionality;
- Vite UI changes that should reach users;
- packaging, PyInstaller spec, updater, or release workflow changes.

Do not release just to test a UI/docs/data workflow change. Use dev modes from
[`development.md`](development.md).

## Required Checks

Before publishing:

```powershell
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
python scripts/data/check_storage_budget.py
python scripts/data/check_managed_ingestion_contracts.py --require-manifests
python -m py_compile desktop/app.py desktop/bridge.py
pytest tests -q
```

Run `pytest apps/api/tests -q` if `apps/api` or shared API contracts changed.

`check_storage_budget.py` enforces the local storage guardrail documented in
[`build-release.md`](build-release.md). Retained rollback backups are warnings
unless the release explicitly opts into `--fail-on-backups`.

`check_managed_ingestion_contracts.py --require-manifests` enforces that large
managed analytical stores have registered contracts and valid local manifests,
so future heavy sector ingestion cannot silently fall back to monolithic SQLite
detail tables.

Manual release validation must include packaged app launch, clean install,
update over previous version, offline already-downloaded data read, updater
no-network/latest-version states, and Excel open-without-repair.

See [`build-release.md`](build-release.md) for the full checklist.
