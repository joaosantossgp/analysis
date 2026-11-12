# Project Status

Short, current snapshot of where the project stands. Update this file whenever
the version, release state, active work, or a major decision changes. Keep it
under one screen; link to canonical docs instead of repeating them.

Last updated: 2026-11-12

## Version and releases

- Runtime version (`desktop/__version__.py`): `0.30.0-rc.1`.
- Latest stable release: `v0.29.2` (2026-07-09).
- Latest prerelease: `v0.30.0-rc.1` (2026-07-16).
- Release workflow: enabled. Follow `docs/release-process.md` and
  `docs/build-release.md`.

## Production and external writes

Enabled. The temporary suspension from #456 (2026-08-25) was reverted on
2026-10-29. Landing deploy, ingestion, catalog seed, and desktop release
workflows run as defined in `.github/workflows/`.

The scheduled monthly refresh (`refresh.yml`) and quarterly gap-fill
(`backfill_historico.yml`) were disabled on 2026-10-29: their external
PostgreSQL (`DATABASE_URL`) is over its 512 MB plan limit and every scheduled
run since 2026-05 failed. Both remain available through manual dispatch.

## Active work

- #489 delivered repeated/backward-clock current reads in the sandbox entity registry
  while preserving explicit historical boundaries. Deterministic Windows tests
  cover the five previously intermittent failures; no user-data repair or
  runtime registry activation is included.

- #483 delivered conservative financial period QA, source/lineage persistence
  and visible read/export evidence. Existing user data requires an explicit
  scoped refresh; no bulk repair or release is implied. See
  [financial contracts](CONTEXT.md#dre-and-dfc-rules).
- #484 delivers bounded annual source reuse for two compatible persistent refresh
  jobs, with a 60-second admission window and 128 MiB retained-subset budget;
  individual job and financial contracts are preserved. See
  [refresh architecture](architecture.md#service-and-coverage-boundaries).
  Controlled three-pair measurements preserved all financial/QA hashes and cut
  queue time by 13.7% (one year) and 16.7% (three years); three-year resident
  memory fell from 2.68 to 1.29 GiB, with unchanged disk footprint. See
  [validation evidence](research/2026-11-11-bounded-refresh-validation.md).
  Bounded packaged evidence is recorded under #485 below.
- #492 removes redundant audit-metadata copies from financial persistence and
  ingestion workbooks. Three pairs per scope reduced queue time by 48.1% (one
  year) and 57.1% (three years), preserving financial/QA hashes and 24 workbook
  contents. No RAM or disk improvement is claimed. See
  [validation evidence](research/2026-11-11-audit-copy-overhead-validation.md).
- #485 validated the exact post-#492 package on the available Windows host:
  primary run 03 passed scoped UI import, storage error/retry, graceful
  backup/restore and offline reads. Supplemental run 04 supplied four populated
  chart reads during another import, but remains failed at final monitor cleanup;
  its higher memory peak and sampling gaps are disclosed. See
  [packaged evidence](research/2026-11-12-packaged-local-data-validation.md).
  The owner's 8 GB RAM / 30 GB free disk reference is an efficiency guide, not
  a mandatory hardware or VM gate. No release or crash-durability claim follows.
- #495 extends the existing bounded source context to ordinary standalone
  refresh jobs. Three controlled pairs reduced three-year resident memory from
  2.672 to 1.425 GiB, preserving all financial/QA hashes and 24 workbooks.
  Three-year throughput and disk footprint were unchanged; exact packaged
  validation passed. See the
  [validation evidence](research/2026-11-12-standalone-source-memory-validation.md).
- Initial multi-window and local-storage desk research is published under #465;
  see `docs/research/2026-11-04-multi-window-workbench.md` and
  `docs/research/local-multi-window-storage.md`. Goal #464 remains open.
  Planning and validation #466 still require product choices, workload
  benchmarks and packaged recovery/offline evidence before implementation.
- Eleven upstream agent skills are versioned (#463). Updates are manual and
  explicitly requested (#469); CI only verifies integrity and regression tests.
  No publication token is required; see `docs/agents/skills.md`.

- Backlog was reset on 2026-10-29: 30 stale issues were closed as not planned.
- #486 tracks the company-to-Excel cycle. #480 delivered storage scan UI
  completion/error handling in PR #488; see [validation](governance/2026-11-11-storage-scan-ui-validation.md).
- #452 applies explicit Companies ordering to the full enriched local directory
  before pagination, with missing-last values and deterministic CVM ties.
  Existing callers without an explicit order retain their defaults. See
  [validation](governance/2026-11-12-company-directory-sorting.md).
- #487 / PR #499 now implement the approved #500 simplification: Home retained,
  News UI retired without deleting saved data, Coverage and asset mapping inside
  Companies, and source health inside Settings. Sectors/Indicators retain unique
  analytical tools. Frontend and browser evidence is recorded in the
  [candidate record](governance/2026-11-12-company-focus-ui.md).
  Exact integrated desktop/Excel/offline acceptance remains pending; #487 and
  #486 stay open. External #483-485 evidence remains artifact-specific.
- Next for #464: resolve #466, record the architecture decision and create
  scoped implementation sub-issues. No shell or storage migration is approved.

## Recent decisions

| Date | Decision |
|---|---|
| 2026-11-06 | Windows storage persistence (#477) passed targeted packaged validation (#479): repeated scans, real reader contention, failure preservation and cached restart. UI completion/error gaps were subsequently resolved by #480 (PR #488); full release acceptance is not claimed. See [evidence](governance/2026-11-06-packaged-storage-validation.md). |
| 2026-11-05 | Runtime reliability fixes merged in #472 (closes #471): local catalog reads, atomic API job admission/cancellation, single-worker container and API tests in CI. Packaged/hosted validation remains separate. |
| 2026-11-05 | Maintenance boundaries clarified (#475): explicit refresh/mapping command modules and Coverage workspace components; public service/route contracts preserved. |
| 2026-11-05 | Contributor contracts aligned (#473): current UI tokens, explicit mock mode, project-interpreter commands and skill-independent agent workflow. |
| 2026-11-05 | Vendored skills use occasional manual updates; scheduled refresh and automated PR publication removed (#469). |
| 2026-10-29 | Production freeze (#456) reverted. |
| 2026-10-29 | Stale repo skills removed (`skills/`, `.github/skills/`). |
| 2026-10-29 | Issue-driven workflow adopted: goals with sub-issues, `Closes`/`Refs` PR rule, Matt Pocock triage labels, Superpowers + Ponytail + Matt Pocock skills (see `AGENTS.md` Workflow). Lanes/autonomous mode archived. |
| 2026-10-29 | Scheduled monthly refresh and quarterly gap-fill disabled (external PostgreSQL full). |
| 2026-10-29 | Canonical Entity Registry epic (#413) and v0.31.0 plan withdrawn; related decision docs kept for reference only. |
| 2026-10-29 | All documentation must be English (see `AGENTS.md` Language). |
| 2026-10-29 | Docs consolidated: one repository map, one development guide, point-in-time audits/plans archived under `docs/archive/planning-2026/`, domain contracts moved out of `AGENTS.md` into `docs/data-sources.md`. |

## Known documentation debt

- Portuguese docs pending translation: `docs/reference/v2-api-contract.md`,
  `docs/governance/on-demand-release-evidence.md`, and ADRs 0001-0006 in
  `docs/decisions/`.
