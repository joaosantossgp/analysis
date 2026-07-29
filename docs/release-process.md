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

Release Desktop is manual-only and runs two separate phases from `main`:

1. Dispatch **candidate** with the version, full candidate SHA, and its
   already-existing `v<version>` tag. It rejects malformed stable/RC versions,
   a non-main SHA, a tag target mismatch, or any missing/failed/cancelled/latest
   exact-SHA `push/main` CI. The Windows build runs once and uploads immutable
   package and candidate-evidence artifacts.
2. Complete the local-data and packaged-app validations against that downloaded
   candidate ZIP. Store each result as an immutable Actions artifact containing
   a candidate-bound `release-evidence-attestation.json` record. Create typed
   API, CCEE, and strict-backup decision attestations too; each declares
   `required` or `not-required` with a candidate-diff or release-policy basis.
   Pass the five numeric artifact IDs to publish. URLs, comments, and free-form
   references are rejected.
3. Dispatch **publish** with the same version/SHA, candidate run ID, and the
   evidence declarations. It downloads the candidate ZIP and evidence from that
   run, rechecks tag/SHA/latest CI before and after approval, verifies the ZIP
   checksum, uploads publication evidence, and only then publishes. It never
   rebuilds the bundle or creates/moves a tag.

The final publish job is protected by the `release-publication` GitHub
environment. Before use, configure that environment with João
(`joaosantossgp`) as required reviewer and a selected-branch policy that allows
only protected `main`, with administrator bypass disabled. This remote
configuration is a precondition: the workflow has no authority to configure
environments, and its YAML reference alone cannot provide protected approval.
Do not substitute the existing unprotected `Production` environment.

Any failed, cancelled, missing, expired, stale, tag-mismatched, or
checksum/evidence-mismatched gate stops publication. Do not retry by rebuilding
or retagging. Start a new candidate only when the intended source or immutable
candidate itself has changed; otherwise correct the missing evidence and run the
publish phase against the original candidate artifact.

See [`build-release.md`](build-release.md) for the full checklist.
