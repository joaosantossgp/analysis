# Project Status

Current snapshot, updated when release state, active work or a major decision changes.
Keep detail in the owning contract or dated evidence. Last updated: 2026-11-26.

## Version and releases

- Runtime version: `0.30.0-rc.1` (`desktop/__version__.py`).
- Latest stable: `v0.29.2` (2026-07-09); prerelease: `v0.30.0-rc.1` (2026-07-16).
- Later source changes are not a new published release yet.
- Publishing follows [ADR 0011](decisions/0011-build-once-publications-and-update-channels.md):
  since #629, a merge to `main` publishes by shipping class through the
  build-once workflow, a low-risk pre-release with no approval and everything
  else after the owner's approval in `release-publication`
  ([release process](release-process.md)). The first publication, `0.30.0`, is
  #633; promotion, installer, candidate test command and retention are #630-#632
  and #634. Protection (`main` branch protection + `release-publication`
  required reviewer) re-verified 2026-11-27; see
  [remote publication protection](build-release.md#remote-publication-protection).

## Production and external writes

- The temporary production freeze was reverted on 2026-10-29. Manual ingestion,
  catalog seed, landing deployment and release workflows remain defined.
- Monthly refresh and quarterly gap-fill schedules remain disabled after external
  PostgreSQL quota failures; manual dispatch remains available. Current external
  database health has not been revalidated by the documentation audit.

## Active work and direction

- [GitHub Issues](https://github.com/joaosantossgp/analysis/issues) owns live work status.
- Evolve the existing app through scoped analyst improvements. Multi-window work,
  shell/storage migration and the withdrawn entity-registry plan are not approved;
  see [delivery direction](PRODUCT_DIRECTION.md#delivery-direction-2026-11-13).
- The [maintenance audit](research/2026-11-16-documentation-architecture-governance-audit.md)
  records the first round (#509-#511). Later CI/refactoring recommendations remain proposals.
- Canonical company classification delivered (#516, #517-#525): one curated GICS
  sub-industry per active CVM company, local analyst edits, explicit B3 sector source,
  and `setor_analitico` removed. Decision: [ADR 0009](decisions/0009-curated-gics-classification.md);
  contract: [GICS classification](reference/gics-import.md). The curated dataset was
  accepted without row-by-row review (`accepted_without_review`); low-confidence rows are
  the first candidates for correction. Next proposed cycle: Excel mapping account tree
  and presets attached to GICS levels (not yet specified as issues).
- Shell-owned data updates (goal #539, closed 2026-11-26, [ADR 0010](decisions/0010-shell-owned-data-updates.md)):
  all sub-issues delivered. The [packaged validation](governance/2026-11-26-data-journey-packaged-validation.md)
  (#550) passed the first-launch, progressive download, cancel, Stale, offline-launch and
  update-check states on a partial run. It found six bugs (#575-#580). All are fixed and
  [passed a packaged re-check](governance/2026-11-26-data-journey-packaged-validation.md#packaged-re-check-after-the-fixes)
  (build `0378696`):
  - #575: bridge reads no longer pause on the browser `offline` event.
  - #576: the local database pill and empty-database hero appear in about 0.3 s, not 30 s.
  - #577: an open Companies directory follows a running data update.
  - #578: the run ETA uses the whole company phase (20 min shown vs 19 min measured).
  - #579: Home keeps the hero until the first full data update ends.
  - #580: a start that cannot reach CVM is a Failed data update on every surface.
  A full first run to completion has not been done in the packaged app.
- First data update cost (goal #574, #582-#587): QA log scope index, QA events stored as
  source observation ids, DMPL/DVA no longer read, batched evidence inserts, and five unused
  `financial_reports` indexes dropped. A full fresh first run (655 active companies,
  2022-2026, official CVM, dev runtime) now takes **17 minutes**, with a flat pace (about
  27 companies with statements per minute from start to end), and ends with a **5.4 GB**
  database (storage budget check passes). Before: well over 2 hours and 10.7 GB for the same
  436 companies with statements and the same 2.37M financial rows. The default scope
  (ADR 0010) stays unchanged. A full run was not done in the packaged app; the 5-minute
  packaged re-check of #575-#580 showed about 4 s per company early in the run (ETA about
  44 min), against about 2 s in the dev runtime at the same point. Decision (#589): DMPL is
  not persisted; its never-filled export, mapping and API paths were removed.

- Decided 2026-11-26, not yet implemented: a dev-mode goal (#607, tasks #608-#614:
  auto-restart on Python changes, shared/isolated dev data, worktree switch, dev
  panel) and a publishing goal, not yet filed as issues (plain version numbers,
  update channels, shipping classes, build-once promotion, installer). Publishing
  decision: [ADR 0011](decisions/0011-build-once-publications-and-update-channels.md);
  vocabulary: [GLOSSARY.md](../GLOSSARY.md). The current release gate stays in
  force until ADR 0011 is implemented.

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
