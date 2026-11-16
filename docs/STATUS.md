# Project Status

Current snapshot, updated when release state, active work or a major decision changes.
Keep detail in the owning contract or dated evidence. Last updated: 2026-11-16.

## Version and releases

- Runtime version: `0.30.0-rc.1` (`desktop/__version__.py`).
- Latest stable: `v0.29.2` (2026-07-09); prerelease: `v0.30.0-rc.1` (2026-07-16).
- Later source changes are not a new published release. Follow [build/release](build-release.md).
- The release workflow is enabled, but its documented remote approval protection
  is not established. See [observed configuration](build-release.md#remote-publication-protection).

## Production and external writes

- The temporary production freeze was reverted on 2026-10-29. Manual ingestion,
  catalog seed, landing deployment and release workflows remain defined.
- Monthly refresh and quarterly gap-fill schedules remain disabled after external
  PostgreSQL quota failures; manual dispatch remains available. Current external
  database health has not been revalidated by the documentation audit.

## Active work and direction

- [GitHub Issues](https://github.com/joaosantossgp/analysis/issues) owns live work status.
  [#512](https://github.com/joaosantossgp/analysis/issues/512) tracks the owner's remote-protection decision.
- Evolve the existing app through scoped analyst improvements. Multi-window work,
  shell/storage migration and the withdrawn entity-registry plan are not approved;
  see [delivery direction](PRODUCT_DIRECTION.md#delivery-direction-2026-11-13).
- The [maintenance audit](research/2026-11-16-documentation-architecture-governance-audit.md)
  records the first round (#509-#511). Later CI/refactoring recommendations remain proposals.

## Validation and historical evidence

- [Local-data evidence](research/2026-11-13-local-data-evidence-review.md) records
  delivered QA, refresh and packaged follow-ups with artifact-specific limits.
- [Company-focused UI evidence](governance/2026-11-12-company-focus-ui.md) records
  the accepted navigation/export changes. Waived packaged offline and fresh-sandbox
  update checks were not passed tests; no new release acceptance follows.
- [Previous status snapshot](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/STATUS.md)
  preserves completed-work details, measurements, decisions and owner waivers.

## Known documentation debt

- Portuguese remains in the API reference, on-demand release evidence and ADRs
  0001-0004/0006. Translate when touching them; all new documentation is English.
