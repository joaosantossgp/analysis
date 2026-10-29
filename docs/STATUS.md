# Project Status

Short, current snapshot of where the project stands. Update this file whenever
the version, release state, active work, or a major decision changes. Keep it
under one screen; link to canonical docs instead of repeating them.

Last updated: 2026-10-29

## Version and releases

- Runtime version (`desktop/__version__.py`): `0.30.0-rc.1`.
- Latest stable release: `v0.29.2` (2026-07-09).
- Latest prerelease: `v0.30.0-rc.1` (2026-07-16).
- Release workflow: enabled. Follow `docs/release-process.md` and
  `docs/build-release.md`.

## Production and external writes

Enabled. The temporary suspension from #456 (2026-08-25) was reverted on
2026-10-29. Landing deploy, scheduled refresh, quarterly gap-fill, ingestion,
catalog seed, and desktop release workflows run as defined in
`.github/workflows/`.

## Active work

- Backlog was reset on 2026-10-29: 30 stale issues were closed as not planned.
- Open: #452 (apply Companies directory sorting in the backend before
  pagination).
- Next: choose product direction from `docs/PRODUCT_DIRECTION.md` and the
  current app state, then open new issues.

## Recent decisions

| Date | Decision |
|---|---|
| 2026-10-29 | Production freeze (#456) reverted. |
| 2026-10-29 | Canonical Entity Registry epic (#413) and v0.31.0 plan withdrawn; related decision docs kept for reference only. |
| 2026-10-29 | All documentation must be English (see `AGENTS.md` Language). |
| 2026-10-29 | Docs consolidated: one repository map, one development guide, point-in-time audits/plans archived under `docs/archive/planning-2026/`, domain contracts moved out of `AGENTS.md` into `docs/data-sources.md`. |

## Known documentation debt

- Portuguese docs pending translation: `docs/reference/v2-api-contract.md`,
  `docs/governance/on-demand-release-evidence.md`, and ADRs 0001-0006 in
  `docs/decisions/`.
- `skills/doc-architect/SKILL.md` describes an older Streamlit dashboard
  layout (`dashboard/app.py`, `MEMORIADASIA.md`) and looks stale.
