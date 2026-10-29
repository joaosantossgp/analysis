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
| 2026-10-29 | All documentation must be English (see `AGENTS.md` Language Policy). |

## Known documentation debt

- Overlapping repository maps: `docs/active-project-map.md`,
  `docs/reference/repository-map.md`, `docs/architecture.md`.
- Overlapping run guides: `docs/COMO_RODAR.md` (Portuguese),
  `docs/development.md`, `docs/dev-runtime-and-data-paths.md`.
- Point-in-time audits and plans in the `docs/` root and planning prompts in
  `docs/reference/` should move to a dated archive.
- `AGENTS.md` repeats domain contracts that live in other docs.
- Portuguese docs pending translation, including `docs/PRODUCT.md` and
  `docs/COMO_RODAR.md`.
