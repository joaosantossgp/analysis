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
python scripts/data/check_managed_ingestion_contracts.py --require-manifests --scan-sqlite-large-tables
python -m py_compile desktop/app.py desktop/bridge.py
pytest tests -q
```

Run `pytest apps/api/tests -q` if `apps/api` or shared API contracts changed.

`check_storage_budget.py` enforces the local storage guardrail documented in
[`build-release.md`](build-release.md). Retained rollback backups are warnings
unless the release explicitly opts into `--fail-on-backups`.

`check_managed_ingestion_contracts.py --require-manifests --scan-sqlite-large-tables`
enforces that large managed analytical stores have registered contracts, valid
local manifests, bounded read plans, and explicit classifications for any large
SQLite tables. Planned registrations do not require manifests until a real
importer exists, so future heavy sector ingestion cannot silently fall back to
monolithic SQLite detail tables.

Manual release validation must include packaged app launch, clean install,
update over previous version, offline already-downloaded data read, updater
no-network/latest-version states, and Excel open-without-repair.

## Exact-SHA Candidate and Publication Gate

Release Desktop is manual-only and runs three separate phases from `main`:

1. Dispatch **candidate** with the version, full candidate SHA, and its
   already-existing `v<version>` tag. It rejects malformed stable/RC versions,
   a non-main SHA, a tag target mismatch, or any missing/failed/cancelled/latest
   exact-SHA `push/main` CI. The Windows build runs once and uploads immutable
   package and candidate-evidence artifacts.
2. Complete local-data and packaged-app validations against that downloaded
   candidate ZIP. Dispatch **attest** with the same version/SHA, candidate run
   ID, manual summaries, and typed API, CCEE, and strict-backup decisions.
   Attest only runs when the dispatch itself is trusted `main` at that exact
   SHA; it rechecks candidate artifact/checksum binding and emits the five
   named candidate-bound records.
3. Dispatch **publish** with the same version/SHA, candidate run ID, and the
   successful attest run ID. It accepts records only from that successful
   `Release Desktop` attest run at trusted `main` and the exact candidate SHA,
   rechecks tag/SHA/latest CI before and after approval, verifies the ZIP
   checksum, uploads publication evidence, and only then publishes. It never
   rebuilds the bundle or creates/moves a tag.

The final publish job is protected by the configured `release-publication`
GitHub environment. Do not substitute the unprotected `Production` environment
or weaken its remote reviewer, protected-branch, or bypass settings.

Any failed, cancelled, missing, expired, stale, tag-mismatched, or
checksum/evidence-mismatched gate stops publication. Do not retry by rebuilding
or retagging while the accepted candidate artifacts remain available; correct
missing evidence and run publish against that original candidate artifact.

The sole retention exception is a fresh candidate cycle for the **same
version/SHA only after artifact expiry**. It creates **new immutable artifacts
and run IDs**, and must repeat **exact-SHA CI, package/manual/conditional attestations,
and #440 approval**, and can publish only that replacement candidate. Keep the
expired run IDs as **superseded evidence** in the release record; they cannot be
reused by attest or publish. This exception does not permit a new tag, retag, or
substitution while the original immutable artifacts are still available.

See [`build-release.md`](build-release.md) for the full checklist.
