# GO Decision — Coverage Universe Phase 0

## Decision

**GO for Phase 0A and Phase 0B only.**

Do not revise the full plan again. This note supersedes any conflicting wording in the existing plan.

Phases 1–5 remain approved as direction only and must not be implemented in this release.

## Binding execution rules

### 1. Canonical market cap

Use the existing canonical local market-cap snapshot/service keyed by `cd_cvm`.

Do not use `company_universe.selected_preset = 'all'` as the canonical market-cap source when that preset contains catalog rows without market cap.

Do not:

- use unordered `LIMIT 1`;
- synthesize market cap from price;
- sum market caps across tickers or share classes without evidence that the values are non-overlapping components.

Return market cap source, source date, cache/download timestamp, method, provider status, currency, and stale status when available.

### 2. Holdings containment

Phase 0B must not pretend that the current numeric default distinguishes confirmed 0% from unknown.

Until the Phase 1 holdings migration exists:

- treat the holding factor as missing unless the current record is explicitly proven to be user-entered or imported;
- do not interpret a default `0.0` as confirmed zero;
- renormalize the remaining valid factors;
- expose the holding factor as missing in the response and UI.

The full holdings schema and migration remain in Phase 1.

### 3. Scoring states

Implement:

- `complete`;
- `partial`;
- `blocked`.

A score is blocked when:

- available original weights total less than 50%; or
- only one factor is available; or
- sector complexity is the only available factor.

Blocked companies receive no numeric final score, remain visible, sort below ranked companies, and display the missing factors.

A manual override must not unblock a blocked score.

### 4. Liquidity

Remove the synthetic market-cap fallback and any now-unused “latest price” query.

Define company liquidity as:

1. `volume × raw close` for each ticker and trading date;
2. sum ticker values by company and date;
3. average company daily traded value over the configured window.

Use BRL units and require a documented minimum number of valid observations.

Treat the previous latest-price finding as part of the liquidity correction, not as a separate feature.

### 5. Score delta containment

Do not describe the current issue as a checklist crash unless reproduced.

For Phase 0B:

- hide or disable the delta display;
- stop writing score snapshot events from checklist-only changes;
- preserve normal checklist decision-history events;
- add regression tests.

The structured snapshot table remains Phase 1.

### 6. Universe deletion

Phase 0B must include:

- archive as the primary action;
- permanent deletion only in a secondary Danger Zone;
- explicit confirmation;
- one database transaction;
- explicit deletion of Coverage child rows in safe dependency order;
- rollback on any failure;
- verification that the deleted universe leaves no Coverage child rows.

Global connection-level foreign-key enforcement, orphan cleanup, backup, and restore remain Phase 1.

### 7. Packaged runtime

Treat PyInstaller failure as unverified.

Run the packaged smoke test. Do not add defensive hidden imports unless:

- the packaged build fails; or
- PyInstaller analysis output proves the modules are missing.

### 8. Performance

Measure the current query count and latency.

Do not include N+1 optimization in the Phase 0B release unless the baseline shows a material regression or unacceptable load time.

## Phase 0A — Required evidence

Capture only the evidence needed to implement and validate Phase 0B:

- current branch and HEAD;
- active runtime confirmation;
- resolved database path;
- packaged Coverage smoke result;
- current score fixtures;
- canonical market-cap source inspection;
- orphan counts;
- current query-count baseline;
- current Excel open/integrity result.

Phase 0A must not change production behavior.

## Phase 0B — Approved implementation scope

Implement only:

1. deterministic canonical market-cap lookup;
2. removal of synthetic market cap;
3. explicit missing-factor metadata;
4. complete/partial/blocked score behavior;
5. temporary safe handling of unknown holdings;
6. BRL daily liquidity aggregation;
7. canonical GICS slug for complexity;
8. removal of hardcoded peers and drivers;
9. score-delta containment;
10. archive-first workflow;
11. transactional permanent deletion;
12. focused regression tests;
13. required UI states and source/freshness disclosure for touched factors.

Do not implement in this release:

- structured score snapshots;
- global foreign-key migration;
- orphan deletion migration;
- Analyst Profile;
- capacity scenario CRUD;
- owner management;
- Excel redesign;
- event-driven Work Queue;
- correlation;
- relationship mapping;
- methodology templates.

## Minimum validation

Run and report the actual commands supported by the repository, including at minimum:

```bash
pytest tests/test_coverage_universe.py -q
pytest tests/ -q
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
```

Also validate:

- missing market cap;
- missing GICS;
- unknown holding;
- confirmed available factors;
- partial score;
- blocked score;
- multiple market-cap candidates;
- multiple ticker/date liquidity aggregation;
- checklist update creates no score snapshot;
- archive preserves data;
- hard delete leaves no Coverage child rows;
- failed hard delete rolls back;
- dev runtime;
- packaged executable;
- offline use with already-downloaded data;
- Excel export still opens without repair.

Do not claim a validation passed unless it was executed.

## Release acceptance criteria

Phase 0 is complete only when:

1. no synthetic financial value remains in priority scoring;
2. market cap selection is deterministic and auditable;
3. missing inputs are visible and never silently converted to zero;
4. blocked companies do not receive misleading rankings;
5. liquidity uses company daily traded value in BRL;
6. complexity uses canonical GICS identifiers;
7. hardcoded peers and drivers are gone;
8. checklist updates no longer create invalid score snapshots;
9. archive is the default removal workflow;
10. permanent deletion is transactional and leaves no Coverage child rows;
11. targeted tests, full Python tests, frontend typecheck, and frontend build pass;
12. the packaged Coverage smoke test passes;
13. remaining risks and unvalidated paths are explicitly reported.

## Final report

Report:

- root causes fixed;
- files changed;
- schema changes, if any;
- tests and commands run;
- exact results;
- packaged validation result;
- performance baseline;
- remaining risks;
- deferred Phases 1–5 work.

Proceed with Phase 0A and Phase 0B under these constraints. Stop and report only if repository evidence materially contradicts this approved scope.
