# Project Status

Short, current snapshot of where the project stands. Update this file whenever
the version, release state, active work, or a major decision changes. Keep it
under one screen; link to canonical docs instead of repeating them.

Last updated: 2026-11-05

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

- Eleven upstream agent skills are versioned with weekly update PR tooling
  (#463). Hosted publication still needs the `SKILL_UPDATE_TOKEN` secret and
  a hosted smoke test; see `docs/agents/skills.md`.

- Backlog was reset on 2026-10-29: 30 stale issues were closed as not planned.
- Open: #452 (apply Companies directory sorting in the backend before
  pagination).
- Next: choose product direction from `docs/PRODUCT_DIRECTION.md` and the
  current app state, then open new issues.

## Recent decisions

| Date | Decision |
|---|---|
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
