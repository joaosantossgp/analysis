# Build And Release

## Product Artifact

The shipped product is the Windows desktop bundle:

```text
dist/CVMAnalytics/CVMAnalytics.exe
dist/CVMAnalytics/_internal/
```

The bundle is produced by `desktop/build_desktop.ps1` and PyInstaller using
`desktop/app.spec`.

## Local Build

```powershell
.\desktop\build_desktop.ps1
```

What the build does:

1. Runs `npm run build` in `apps/desktop-web`.
2. Verifies `apps/desktop-web/dist/index.html` exists.
3. Resolves/injects version into `desktop/__version__.py`.
4. Writes build provenance to `desktop/_build_info.py`.
5. Runs `pyinstaller desktop/app.spec --noconfirm`.

`-SkipViteBuild` may be used only after a successful prior Vite build.

The desktop bundle includes the Vite static SPA, Python code/dependencies,
`update_helper.ps1`, and approved import assets such as canonical accounts and
GICS/ticker mapping CSVs. It must not bundle a user database.

## GitHub Release Workflow

`.github/workflows/release-desktop.yml` is a manual, two-phase release gate.
It does not run on tag push. Both phases must be dispatched from `main` with a
full 40-character `candidate_sha`, a supported version, and an already-existing
matching `v<version>` tag.

1. **Candidate phase** resolves the annotated or lightweight tag to its peeled
   commit target, verifies that it is the exact candidate SHA and is reachable
   from `origin/main`, and requires the latest `CI` `push/main` run for that
   exact SHA to be `completed/success`. The Windows builder checks out that SHA,
   verifies observed `HEAD` before and after the build, verifies the injected
   runtime version and build provenance, then builds only once. It uploads two
   immutable GitHub Actions artifacts: the versioned ZIP/checksum package and
   `candidate-evidence.json`, which records the candidate SHA, tag target,
   observed builder SHA, exact-CI run, package artifact ID, and ZIP checksum.
2. **Attest phase** runs only from trusted `main` at the exact candidate SHA.
   It re-verifies the successful candidate run, immutable artifacts, and
   checksum before producing five named evidence artifacts. Operator summaries
   remain explicitly manual evidence; the workflow attests their provenance and
   candidate binding, not the underlying observation.
3. **Publish phase** accepts the trusted attest run ID, not arbitrary artifact
   IDs. It resolves the five exact artifact names from that run and rejects any
   mismatch in workflow name/path, dispatch event, successful conclusion,
   `main` ref, candidate SHA, Actions metadata, or declared producer fields.
   Before and after protected approval it re-resolves the tag and latest
   exact-SHA CI. The final job downloads the saved candidate and verified
   evidence, verifies identity and checksum, then publishes those bytes without
   rebuilding or retagging.

Only the final `Publish verified candidate` job has `contents: write`; every
other release job has read-only repository permissions. Stable `X.Y.Z` remains
a normal release and `X.Y.Z-rc.N` remains a prerelease. A stable release must
therefore use the approved same-SHA candidate evidence or a separately approved
new candidate; the workflow never promotes a different SHA by tag movement.

Publication uses the protected `release-publication` environment. Its reviewer,
protected-`main` branch policy, and administrator-bypass settings are remote
configuration; do not replace or weaken them in workflow code.

### Artifact-expiry recovery

An expired candidate, candidate-evidence, or attestation artifact cannot be
repaired or published. The recovery exception is a fresh candidate cycle for
the **same version/SHA only after artifact expiry**. It creates **new immutable
artifacts and run IDs**, and must repeat **exact-SHA CI, package/manual/conditional
attestations, and #440 approval**, and publishes only the replacement candidate.
The expired run IDs remain **superseded evidence** in the release record and
cannot be supplied to publish. This exception does not allow rebuilding,
retagging, or substituting artifacts for a candidate whose artifacts remain
available.

Flat-root means the ZIP root contains `CVMAnalytics.exe` and `_internal/`
directly. A wrapper folder breaks the updater contract.

## Version Sources

- `desktop/__version__.py` is the runtime version source.
- `desktop/build_desktop.ps1` may derive a version from `git describe` for local
  builds unless `-Version` is supplied.
- The release workflow supplies the exact version and aborts if the bundled
  version differs.
- `desktop/_build_info.py` is generated build provenance written by the desktop
  build. It is useful for packaged-app diagnostics, but it is not authoritative
  checkout state and may be stale in a source tree until a package build runs.

## Release Evidence Hierarchy

When release evidence conflicts, use this hierarchy:

1. **Immutable candidate evidence** — verify the full candidate SHA, peeled tag
   target, observed Windows-builder SHA, exact `push/main` CI run, immutable
   package artifact ID, and ZIP checksum in `candidate-evidence.json`. The
   publish phase must re-check every value before it creates a release.
2. **Release tag and commit** — verify the checkout with `git describe --tags
   --exact-match HEAD`, `git tag --points-at HEAD`, and `git rev-parse HEAD`.
   The tag target must equal the immutable candidate SHA; no tag is created or
   moved by the release workflow.
3. **Bundled runtime version** — verify `desktop/__version__.py` in the source
   tree or packaged bundle. The release workflow passes the exact version into
   `desktop/build_desktop.ps1 -Version <version>` and fails if the bundled
   runtime version does not match the release input.
4. **Generated build provenance** — inspect `desktop/_build_info.py` or
   Settings -> Diagnostics in the packaged app for generated build commit and
   build timestamp. Treat this as artifact provenance, not as proof of the
   current checkout.
5. **Manual and conditional evidence** — use the verified trusted-attest run,
   expected artifact identities, ZIP/content SHA-256 values, and
   `manual-evidence.json` to prove local-data checks, packaged validation, and
   every required conditional check. A protected-environment approval is not
   evidence that a manual check ran.
6. **Packaged validation evidence** — use the release workflow logs, release
   notes, and manual packaged-app validation records to prove the built artifact
   launched correctly, used the expected data root, handled offline/update
   states, preserved user data, and exported Excel files that open without
   repair.

Each release record should identify tag, commit, bundled runtime version, build
timestamp when available, validation environment, and the results of packaged
launch, updater/offline, and Excel-open checks. It must also identify the
candidate run/artifact IDs and ZIP checksum, and bind its manual/conditional
evidence to those values. User data remains excluded from release artifacts.

### Evidence attestation contract

Dispatch **attest** from `main` at the exact candidate SHA with the candidate
run ID and the operator's manual/conditional summaries. It writes one named,
immutable Actions artifact per record, each containing exactly one UTF-8 JSON
file named `release-evidence-attestation.json`. Publish accepts only the
successful attest run ID. It resolves the five expected artifact names from
that run, then records their IDs, ZIP SHA-256 values, and JSON-content SHA-256
values. It rejects expired, malformed, multi-file, mismatched, or untrusted
producer records.

Every record has this candidate binding:

```json
{
  "schema_version": 1,
  "attestation_type": "manual-local-data",
  "candidate": {
    "candidate_sha": "<40 lowercase hex>",
    "tag_target_sha": "<same SHA>",
    "candidate_run_id": "<candidate Actions run ID>",
    "package_artifact_id": "<candidate package artifact ID>",
    "zip_checksum": "<64 lowercase hex>"
  },
  "producer": {
    "workflow_run_id": "<attestation producer run ID>",
    "phase": "attest",
    "workflow_name": "Release Desktop",
    "workflow_path": ".github/workflows/release-desktop.yml",
    "head_ref": "main",
    "head_sha": "<same SHA>"
  },
  "result": { "manual": true, "summary": "<operator record>" }
}
```

The two required manual `attestation_type` values are `manual-local-data` and
`manual-packaged`. They preserve the manual nature of source-data and packaged
checks: a valid record proves candidate binding and provenance, not that the
workflow independently reproduced every substantive observation.

The three conditional values are `conditional-api`, `conditional-ccee`, and
`conditional-strict-backup`. Each additionally requires a typed decision:

```json
{
  "decision": {
    "status": "required",
    "basis": {
      "type": "candidate-diff",
      "candidate_sha": "<same SHA>",
      "tag_target_sha": "<same SHA>",
      "summary": "<reviewed changed-path/policy explanation>"
    }
  }
}
```

`status` is exactly `required` or `not-required`; basis `type` is exactly
`candidate-diff` or `release-policy`. A required conditional record also needs
the manual `result` object. These typed, candidate-bound attestations replace
free-form applicability strings.

## Updater Contract

Verified implementation:

- `desktop/updater.py` checks GitHub Releases, compares versions, downloads the
  versioned ZIP and `.sha256`, validates checksum, extracts into
  `%LOCALAPPDATA%\CVMAnalytics\versions\<version>\`, and spawns the helper.
- `desktop/update_helper.ps1` swaps only allowlisted bundle entries:
  `CVMAnalytics.exe` and `_internal`.
- The helper snapshots overwritten files to
  `%LOCALAPPDATA%\CVMAnalytics\update_rollback\<utc-ts>\`.
- User data directories are denied by name and are not part of the bundle swap.

### Accepted updater version tags

The updater accepts only a stable `v?MAJOR.MINOR.PATCH` tag or the matching
`-rc.N` prerelease form, with no leading zeros in numeric components. It also
accepts the `git describe` form emitted after a tag:
`<tag>-DISTANCE-g<lowercase-hex>`. `DISTANCE` must be positive
(`[1-9][0-9]*`); an exact tag has no suffix, so `-0-g...` is invalid. Invalid
or malformed tags are ignored and must never be offered as updates even when a
matching release asset exists. Keep parser and both updater-path regressions in
sync when extending this contract.

User data under `%USERPROFILE%\Documents\CVMAnalytics` must not be overwritten
by update/install flows.

## Release Validation

Before publishing:

```powershell
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
python scripts/data/check_storage_budget.py
python scripts/data/check_managed_ingestion_contracts.py --require-manifests --scan-sqlite-large-tables
python -m py_compile desktop/app.py desktop/bridge.py
pytest tests -q
```

Also run `pytest apps/api/tests -q` if `apps/api` or shared API contracts
changed.

The storage budget guardrail fails if local data regresses toward a monolithic
main database layout. Default budgets are:

- any one main SQLite database: 12 GiB;
- all main SQLite databases: 16 GiB;
- active local storage excluding rollback backups: 32 GiB.

Retained rollback backups are warnings by default, not failures. Use
`python scripts/data/check_storage_budget.py --fail-on-backups` only when the
release policy explicitly requires no local rollback backups.

The managed-ingestion contract guardrail verifies that large local-first
analytical stores are registered, have valid contracts, have matching local
manifests under `%USERPROFILE%\Documents\CVMAnalytics`, and do not leave
unclassified large detail tables in the main SQLite databases. It currently
covers the CCEE hourly hot/cold store, MMGD project detail store, and ANP Fuel
Distribution managed store. New heavy sector ingestion must add a managed
registration and bounded read plan before release validation can pass in strict
mode. Planned registrations validate their contracts but do not require
manifests until a real importer exists.

For releases that touch CCEE hourly ingestion or the managed hot/cold store,
run a sandbox ingestion smoke test with a real CCEE hourly snapshot:

```powershell
python scripts/data/smoke_ccee_hourly_managed_ingestion.py `
  --source-file "<Documents>\CVMAnalytics\raw\energy\plant_parcels\ccee_plant_generation_hourly\<snapshot>\geracao_horaria_usina_YYYYMM.csv.gz" `
  --reference-month YYYY-MM
```

The default smoke test copies the compact `energy_kpis.db` and the managed hot
SQLite artifact into a temporary sandbox, removes duplicate import-log rows only
inside that sandbox, and verifies that ingestion updates the managed store and
marts while `ccee_plant_parcel_hourly` in the main database remains empty. Do
not use `--apply` unless the release operator intentionally wants to import into
the live Documents data root.

The managed hourly store keeps a bounded hot SQLite window. Ingestion defaults
to two hot months unless `selection.max_hot_months` is set in the manifest; when
that limit is exceeded, older hot months are exported to cold Parquet partitions
and removed from hot SQLite. The smoke report therefore reconciles total managed
rows for the imported month across hot and cold storage.

Managed hourly imports also write `storage_telemetry_json` to
`energy_source_refresh_log`. It records before/after main DB bytes, hot SQLite
bytes, cold Parquet bytes, manifest row counts, hot/cold month lists, and mart
rebuild row counts. Use this field when reviewing storage impact after a heavy
import.

Manual packaged validation:

- clean launch from `dist/CVMAnalytics/CVMAnalytics.exe`;
- app uses `%USERPROFILE%\Documents\CVMAnalytics`, not install-local data;
- Settings -> Diagnostics shows expected version/build/data paths;
- empty database state is understandable and non-crashing;
- offline read of already-downloaded data works;
- update check handles no-network and latest-version states explicitly;
- Excel export from the packaged app writes to output and opens without repair;
- install/update over a previous version preserves user data;
- update helper keeps ZIP root contract and rollback snapshot behavior.

## What Does Not Require A Release

Do not cut a release merely to test ordinary UI/docs/data workflow changes.
Use dev modes from [development.md](development.md).

Release only when installed users need the change or when packaging/updater
behavior changes.
