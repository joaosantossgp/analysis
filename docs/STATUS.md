# Project Status

Short, current snapshot of where the project stands. Update this file whenever
the version, release state, active work, or a major decision changes. Keep it
under one screen; link to canonical docs instead of repeating them.

Last updated: 2026-11-11

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

- #483 implements conservative financial period QA, source/lineage persistence
  and visible read/export evidence. Existing user data requires an explicit
  scoped refresh; no bulk repair or release is implied. See
  [financial contracts](CONTEXT.md#dre-and-dfc-rules). #484 follows this fix.
- Initial multi-window and local-storage desk research is published under #465;
  see `docs/research/2026-11-04-multi-window-workbench.md` and
  `docs/research/local-multi-window-storage.md`. Goal #464 remains open.
  Planning and validation #466 still require product choices, workload
  benchmarks and packaged recovery/offline evidence before implementation.
- Eleven upstream agent skills are versioned (#463). Updates are manual and
  explicitly requested (#469); CI only verifies integrity and regression tests.
  No publication token is required; see `docs/agents/skills.md`.

- Backlog was reset on 2026-10-29: 30 stale issues were closed as not planned.
- Open: #452 (apply Companies directory sorting in the backend before
  pagination).
- Next for #464: resolve #466, record the architecture decision and create
  scoped implementation sub-issues. No shell or storage migration is approved.

## Recent decisions

| Date | Decision |
|---|---|
| 2026-11-06 | Windows storage persistence (#477) passed targeted packaged validation (#479): repeated scans, real reader contention, failure preservation and cached restart. UI completion/error gaps remain in #480; full release acceptance is not claimed. See [evidence](governance/2026-11-06-packaged-storage-validation.md). |
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
