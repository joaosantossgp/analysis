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

## Publication Workflow

`.github/workflows/release-desktop.yml` builds and publishes every
publication. The flow, the approval rule and how an agent approves for the
owner are in [`release-process.md`](release-process.md); this section is the
build and integrity contract.

- **Trigger.** A successful `CI` run for a push to `main` (`workflow_run`), or a
  manual `workflow_dispatch` (dry run by default). The decision comes from
  `scripts/release/publication_decision.py decide`, fed by
  `scripts/release/publication_workflow.py facts`; class `none` builds nothing.
- **Exact commit, green CI.** The candidate is the newest first-parent `main`
  commit after the last publication whose latest `push`/`main` CI run is
  `completed/success`. The Windows builder checks out that commit and verifies
  `HEAD` before and after the build.
- **Build once, version stamped at build time.** The builder runs
  `desktop/build_desktop.ps1 -Version <decided version>` and fails unless
  `desktop/__version__.py` holds that version and `desktop/_build_info.py`
  holds the candidate commit. Nothing is committed to `main`; the source-tree
  version stays a dev fallback.
- **One file, verified at publication.** The build job packages
  `CVMAnalytics-windows-v<version>.zip` (flat root checked) and its `.sha256`,
  keeps them as the run's `publication-candidate` artifact and records the
  hash as a job output. The publish job downloads that artifact from the same
  run, checks the hash against the `.sha256` file and the build job's output,
  adds the unversioned `CVMAnalytics-windows.zip` pair, and publishes those
  bytes. No publish job builds, packages from source, commits or pushes.
- **Tag with the release.** `gh release create v<version> --target <commit>`
  creates the tag on the exact candidate commit together with the release, as a
  pre-release (`--latest=false`) or a release (`--latest=true`). A candidate
  that is rejected, superseded or cancelled leaves no tag. The last publication
  is read from published releases, never from bare tags.
- **Least privilege.** The workflow default is `contents: read`. Only
  `publish-automatic` (a pre-release outside the risk areas) and
  `publish-approved` (everything else, in the `release-publication`
  environment) have `contents: write`. Dispatch inputs reach scripts as
  environment variables, never as interpolated shell code, and every action is
  pinned to a full commit SHA.

Flat-root means the ZIP root contains `CVMAnalytics.exe` and `_internal/`
directly. A wrapper folder breaks the updater contract.

### Remote publication protection

`publish-approved` names the `release-publication` environment. The reviewer
and branch protections are remote configuration, separate from the workflow's
commit and checksum checks.

After the [2026-11-16 audit](research/2026-11-16-documentation-architecture-governance-audit.md#1-high-documented-remote-release-protections-are-not-established)
identified private-repository plan limits, the owner authorized making
`joaosantossgp/analysis` public on GitHub Free and enabling remote controls
([#512](https://github.com/joaosantossgp/analysis/issues/512)). API read-back on
2026-11-25 confirmed the following, and a read-back on 2026-11-27 (#629)
matched it:

- **`main` branch protection:** `main` is the only protected branch in the
  repository (`protected: true`, `enforce_admins: true`,
  `allow_force_pushes: false`, `allow_deletions: false`). Merges require a pull
  request (`required_approving_review_count: 0` for the solo-maintainer flow)
  with up-to-date branch checks (`strict: true`) for `Python core tests`,
  `Python core coverage`, `Windows storage inventory`, `Vite desktop UI`, and
  `validate-pr-issue-contract`.
- **`release-publication` environment:** `can_admins_bypass: false`,
  `deployment_branch_policy: { protected_branches: true, custom_branch_policies: false }`
  (restricting deployments exclusively to `main`), and `required_reviewers`
  configured for owner `joaosantossgp` (`prevent_self_review: false`).

**Scope and limits:** because `joaosantossgp` is the sole repository owner and
`prevent_self_review` is `false`, these controls prevent direct pushes to
`main`, enforce required CI/guardrail checks, restrict approved publications to
`main`, and require an explicit approval by the owner, given in GitHub or
through an agent acting on the owner's explicit OK in chat; they do not provide
two-person separation of duties. A low-risk pre-release publishes with no
approval by design (ADR 0011), from the `publish-automatic` job, which still
runs only for green `main` commits. Re-read the remote configuration before
release work, do not treat green CI as approval, and do not weaken these
controls.

## Version Sources

- `desktop/__version__.py` is the runtime version source of a packaged bundle.
- Publications get their version from the decision module, which computes the
  next plain `MAJOR.MINOR.PATCH` from the last publication and the shipping
  class; the workflow passes it to `desktop/build_desktop.ps1 -Version` and
  aborts if the bundled version differs. There are no version-bump commits.
- Local builds without `-Version` derive a version from `git describe`.
- `desktop/_build_info.py` is generated build provenance written by the desktop
  build. It is useful for packaged-app diagnostics, but it is not authoritative
  checkout state and may be stale in a source tree until a package build runs.

## Publication Record

What proves what a publication contains:

1. **The release page:** tag `v<version>`, the target commit, the kind
   (pre-release or release) and the merged PRs it contains.
2. **The publication run** of `release-desktop.yml`: the decision (`facts.json`
   and `decision.json` in the `publication-decision` artifact), the job summary
   with risk areas and PRs, the build log, the candidate hash, and, when
   approval was required, the `release-publication` deployment approval.
3. **The bundled version and provenance:** `desktop/__version__.py` and
   `desktop/_build_info.py` in the bundle, shown in Settings -> Diagnostics.
4. **Packaged validation:** the owner's test of the candidate before approval,
   recorded in the approval comment or the chat. An approval is a decision, not
   evidence that a particular check ran.

User data remains excluded from every publication.

## Updater Contract

Verified implementation:

- `desktop/updater.py` lists GitHub Releases (`/releases`, newest 100; it no
  longer reads `/releases/latest`), picks the publication for the user's update
  channel (below), downloads the versioned ZIP and `.sha256`, validates
  checksum, extracts into `%LOCALAPPDATA%\CVMAnalytics\versions\<version>\`, and
  spawns the helper.
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

### Update channel and publication selection (ADR 0011, #626)

- The update channel is `releases` (default, "Releases only") or `prereleases`
  ("Pre-releases and releases"). It is stored in
  `%LOCALAPPDATA%\CVMAnalytics\update_channel.json` (`{"channel": "..."}`),
  next to `snooze.json`: outside the bundle and outside the financial database,
  so an update or a data reset keeps it. A missing, unreadable or unknown value
  means `releases`. The file is written to a temporary file and swapped in, so a
  failed write keeps the previous choice.
- Listing: GitHub Releases is read 100 publications per page, newest first,
  until a page holds a publication the channel accepts, at most 5 pages per
  check. A channel with nothing accepted in those pages reads as `no_release`.
- Selection (`select_publication`): drafts and malformed tags are skipped;
  `releases` accepts only publications GitHub marks as releases whose tag has no
  `-rc.N` part (a legacy `-rc.N` tag without the prerelease flag counts as a
  pre-release), `prereleases` accepts both. Versions compare numerically
  (`-rc.N` sorts below the plain version). The offer is the newest accepted
  publication that is newer than the installed version and has its versioned
  ZIP. A version lower than or equal to
  the installed one is never offered, so switching back to `releases` keeps the
  current version until a newer release exists. When no newer publication has
  its ZIP, the status is `asset_missing`.
- Bridge: `get_update_channel` / `set_update_channel` (refused in read-only
  mode). Changing the channel is an explicit user action: it drops the previous
  channel's offer so it cannot be applied, then runs one check for the new
  channel (the same check as `check_update({"force": true})`), logs it to
  `update_error.log` and stores the result; a failed check is stored as
  `check_failed`. `check_update` returns the last known status with `channel`,
  `publication_kind` (`release` / `pre-release`), `checked_at`,
  `current_version` and `latest_version`; `{"force": true}` runs a new check
  (an explicit user action). The `get_app_status().update` payload carries the
  same `channel` and `publication_kind` and never contacts GitHub because of a
  channel change. Besides those user actions, the only check is the one at
  startup.
- Settings -> App shows the channel choice, the pre-release notice, the current
  version and the last check.
- Unchanged: package asset names, checksum validation, staging, the allowlisted
  swap and rollback.

### Shell update announcement (ADR 0011, #627)

- When the stored check offers an update (`check_update().available`), the top
  bar shows an `Update <version>` pill next to the Data pill on every screen,
  marked `pre-release` for a pre-release. It opens a compact panel (closes on
  Escape, a click outside or its close button) with the version, the kind, the
  installed version, the publication page link, **Update now** and **Later**.
- The shell reads only the stored check (`check_update` without `force`), every
  5 s until the startup check has a result, then once a minute; it never
  contacts GitHub. A failed, offline, not-yet-run, up-to-date or postponed check
  shows nothing in the shell; Settings -> App and Advanced -> Software update keep
  the detailed status.
- Nothing is downloaded before **Update now**. It runs the same `apply_update`
  flow as the diagnostics card (shared `useUpdateApply` hook): the pill shows
  `Updating N%`, the panel shows the step (download, checksum, files, restart),
  and the helper restarts the app into the new version. A failure before the
  swap shows `Update failed` with the updater's error; the installed version
  keeps running and **Update now** retries.
- **Later** calls `snooze_update`: the offered tag is postponed for 7 days in
  `snooze.json`, and the stored status becomes `snoozed` with nothing to apply,
  as the next startup check reports it. A newer publication is offered again
  at the next startup.
- Mock preview: `localStorage.setItem("cvm_mock_update", "release_available")`
  (or `prereleases`, `offline`, `snoozed`) before reload; the mock install
  steps through download progress and always ends in a simulated failure.

User data under `%USERPROFILE%\Documents\CVMAnalytics` must not be overwritten
by update/install flows.

## Release Validation

CI runs the automated checks on every candidate commit before it is built. The
checks below are for the owner's test of a candidate before approving it, and
for local runs when a change touches their area:

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

For publications that touch CCEE hourly ingestion or the managed hot/cold store,
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

Manual packaged validation, on the candidate ZIP of the publication run (the
`publication-candidate` artifact), before approving:

- clean launch from the extracted `CVMAnalytics.exe`;
- app uses `%USERPROFILE%\Documents\CVMAnalytics`, not install-local data;
- Settings -> Diagnostics shows expected version/build/data paths;
- empty database state is understandable and non-crashing;
- offline read of already-downloaded data works;
- update check handles no-network and latest-version states explicitly;
- Excel export from the packaged app writes to output and opens without repair;
- install/update over a previous version preserves user data;
- update helper keeps ZIP root contract and rollback snapshot behavior.

## What Does Not Publish

Publications follow the shipping class of merged work
([`release-process.md`](release-process.md#what-a-merge-publishes)): docs, CI,
tests and dev tooling carry `ships:none` and publish nothing. To try a UI, docs
or data workflow change, use dev modes from [development.md](development.md),
not a publication. To try the publication workflow itself, use its dry run.
