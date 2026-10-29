# Prompt — Final Revision of the Coverage Universe Hardening Plan

You are performing the final revision of the current:

**CVMAnalytics Coverage Universe Hardening and Completion Plan**

## Objective

Correct the current plan so it becomes internally consistent, financially sound, migration-safe, and implementation-ready.

This remains a **planning-only task**.

Do not:

- modify source code;
- modify tests;
- modify documentation;
- create or apply migrations;
- create commits;
- open issues or pull requests;
- implement any phase.

Return only the fully corrected replacement plan.

## Repository verification

Before revising the plan, inspect the real current repository and follow:

- `AGENTS.md`
- `README.md`
- `docs/CONTEXT.md`
- `docs/active-project-map.md`
- `docs/reference/repository-map.md`
- `docs/dev-runtime-and-data-paths.md`
- `docs/release-process.md`
- `docs/skills/CVMANALYTICS_VITE_UI_SKILL.md`
- relevant ADRs under `docs/decisions/`

Confirm:

- active frontend;
- pywebview bridge;
- Python service;
- database schema;
- local paths;
- packaging flow;
- Excel export flow;
- relevant tests.

Expected active frontend is `apps/desktop-web`, but verify it.

Do not use archived, removed, prototype, Next.js, or inactive code as the implementation source of truth.

---

# Required corrections

## 1. Reframe the PyInstaller finding

Do not claim that the packaged Coverage module definitely crashes or definitely works.

Static imports make the missing `hiddenimports` less likely to cause a failure, but only a packaged smoke test can confirm runtime behavior.

Use a conclusion similar to:

> Static import analysis suggests Coverage should be collected by PyInstaller, but packaged runtime behavior remains unvalidated.

Classify it as:

- probable packaging-safe;
- runtime unvalidated;
- not a release blocker unless reproduced.

Do not assign “no risk” until the packaged flow is tested.

Required validation:

1. build the Vite app;
2. build the Windows executable;
3. launch it;
4. open Coverage;
5. create a universe;
6. add a company;
7. load prioritization;
8. export Excel;
9. inspect logs.

## 2. Correct the market-cap contract

Do not sum market capitalization across multiple tickers or share classes unless repository data proves that each row represents a non-overlapping component.

The current company-universe model is company-based and may store one row per `selected_preset` and `cd_cvm`.

Define one canonical market-cap observation per company.

The revised plan must specify:

- canonical source;
- canonical preset;
- deterministic row-selection rule;
- source priority;
- `source_date`;
- download or cache timestamp actually available in the repository;
- currency;
- method;
- provider status;
- stale threshold;
- handling of multiple presets;
- handling of multiple tickers;
- handling of multiple share classes;
- conflict resolution;
- missing-data behavior.

Do not use unordered `LIMIT 1`.

Do not invent columns such as `retrieved_at` if they do not exist.

Prefer the canonical local market-cap snapshot contract already present in the repository when appropriate.

## 3. Merge the latest-price issue into liquidity

After removing synthetic market cap, latest price should not remain a separate market-cap blocker.

Treat price only as an input to liquidity unless another verified use exists.

Define liquidity as daily traded value in BRL.

For companies with multiple ticker rows:

1. calculate `share_volume × raw_close_brl` for each ticker and date;
2. aggregate all ticker values to company/date;
3. calculate the average daily company value over the selected window.

Do not calculate one flat `AVG(volume * close)` over all ticker rows without first considering daily company aggregation.

Document:

- `close` versus `adjusted_close`;
- why;
- lookback period;
- minimum valid observations;
- missing days;
- stale history;
- ticker changes;
- splits and corporate actions;
- source;
- source timestamp;
- currency and units.

Remove F04 as an independent blocker if it becomes fully covered by the liquidity correction.

## 4. Correct the score-delta finding

Do not claim checklist actions crash unless reproduced.

The current invalid snapshot conversion is caught, so the observed impact is more likely:

- missing delta;
- invalid baseline;
- semantically invalid records;
- misleading trend display;
- weak auditability.

Phase 0B must contain immediate containment:

- hide or disable the current delta;
- stop writing invalid score snapshot events;
- preserve ordinary decision-history events;
- add regression tests.

The structured snapshot model belongs in Phase 1.

## 5. Add archive-first and transactional delete to Phase 0B

The current plan identifies permanent deletion as a blocker but does not consistently fix it in Phase 0B.

Phase 0B must explicitly include:

- archive as the primary UI action;
- permanent deletion only in a secondary Danger Zone;
- explicit confirmation;
- one database transaction;
- deletion of all Coverage child records in safe order;
- rollback on any error;
- zero orphan rows after completion;
- tests for clean deletion and failed rollback.

The minimum safe release scope must include this containment.

## 6. Add a blocked score state

Renormalization alone is unsafe when only one weak factor is available.

Define:

```text
score_status = complete | partial | blocked
```

The plan must define:

- minimum completeness required for ranking;
- whether any factors are mandatory;
- behavior when only one factor is available;
- behavior when only sector complexity is available;
- ordering of blocked companies;
- UI warnings;
- Excel behavior;
- whether manual override may unblock a score.

Do not allow a single available factor to be renormalized to 100% and presented as a fully meaningful ranking.

## 7. Complete the holdings data contract

The plan must distinguish:

- confirmed zero holding;
- holding not informed;
- holding not applicable;
- stale holding;
- manually entered holding;
- imported portfolio holding.

Evaluate a schema such as:

```text
holding_pct
holding_status
holding_source
holding_as_of_date
holding_updated_at
```

Define stale thresholds and behavior by universe type:

- Equity;
- Credit;
- IB;
- Portfolio Monitoring;
- Sector Watch.

A default numeric `0.0` must not be treated as evidence of a confirmed zero holding.

Include backward-compatible migration from the current field.

## 8. Strengthen snapshot deduplication

Do not deduplicate snapshots only because the final score is unchanged.

Two snapshots with the same final score may have different:

- raw inputs;
- normalized scores;
- weights;
- sources;
- source dates;
- methodology version;
- override;
- trigger.

Define a deterministic payload hash or equivalent comparison over the full relevant snapshot state.

Also define:

- material snapshot triggers;
- no snapshots on checklist-only changes;
- idempotency;
- retention;
- previous baseline selection;
- ordering;
- behavior across methodology versions;
- whether deltas across methodology versions are non-comparable.

## 9. Make orphan cleanup implementation-ready

For every Coverage table, provide:

- detection query or precise detection logic;
- expected relationship;
- cleanup action;
- delete, export, quarantine, or preserve rule;
- order of operations;
- transaction boundary;
- audit log;
- rollback;
- validation.

Cover at least:

- `universe_companies`;
- `coverage_checklists`;
- `coverage_decision_history`;
- `coverage_capacity_scenarios`;
- future `coverage_score_snapshots`;
- rows referencing missing companies;
- checklist rows without matching membership.

Prefer preserving or exporting audit history before destructive cleanup when practical.

## 10. Make backup and restore implementation-ready

Prefer the SQLite Backup API as the primary approach unless repository constraints prove another method safer.

Define:

- timestamped backup path;
- backup directory;
- free-space check;
- WAL handling;
- integrity validation;
- metadata log;
- closing active connections;
- restore procedure;
- restore validation;
- rollback if migration verification fails;
- behavior in packaged and development modes.

Do not describe restore as a simple file rename while the application may hold open connections.

## 11. Choose one Analyst Profile source of truth

Do not store the Analyst Profile simultaneously in both a database table and a local file.

Choose one canonical persistence model, such as:

- existing `app_settings`;
- dedicated local configuration;
- dedicated table.

Explain the decision and trade-offs.

Cover:

- Settings UI;
- bridge methods;
- TypeScript contracts;
- validation;
- editing;
- stable local ID;
- display name or alias;
- optional team and role;
- privacy;
- missing-profile fallback;
- history attribution;
- database move/restore behavior;
- machine migration behavior.

The operating-system username may only be an initial suggestion.

## 12. Complete Phase 2

Phase 2 must include:

- canonical `/coverage/capacity` page;
- owner assignment and editing;
- unassigned-company state;
- owner filters;
- capacity by analyst;
- capacity by team;
- scenario creation;
- scenario duplication;
- scenario activation;
- scenario comparison;
- scenario archive/delete rules;
- exactly one active scenario;
- incremental impact of adding a company;
- source and freshness disclosure;
- complete/partial/blocked score states;
- archive and Danger Zone flows;
- large-universe search, filters, sorting, and grouping;
- virtualization only after measurement;
- loading, empty, error, and missing-data states.

Capacity by analyst is incomplete until owners can be maintained in the UI.

## 13. Complete Phase 4

Phase 4 must define an explicit local-first Work Queue event model.

Include fields for:

- event ID;
- universe ID;
- company ID;
- event type;
- source type;
- source reference;
- source timestamp;
- event timestamp;
- detection timestamp;
- severity;
- status;
- owner;
- due date;
- acknowledgement;
- resolution;
- deduplication key;
- created and updated timestamps.

Define event creation during:

- CVM refresh;
- market-data refresh;
- news import;
- manual reconciliation;
- bounded startup reconciliation only when justified.

Plan:

- idempotent generation;
- deduplication;
- offline behavior;
- local cache;
- no continuous polling without evidence;
- retention;
- acknowledgement;
- resolution;
- reprocessing;
- error logs;
- manual refresh;
- no repeated external calls.

Define “news anomaly” objectively or defer it.

## 14. Complete Phase 5

Phase 5 must clearly separate:

### Price correlation

- returns;
- benchmark-relative correlation;
- periods;
- clusters;
- duplicated market exposure.

### Fundamental similarity

- business model;
- financial profile;
- operating drivers;
- capital structure;
- regulation;
- sector relationships.

### Company relationships

- peers;
- competitors;
- suppliers;
- customers;
- subsidiaries;
- commodities;
- FX;
- interest rates;
- concessions;
- utilities-specific drivers;
- source;
- source date;
- confidence;
- manual override.

### Manager decision support

- current versus proposed universe;
- alternatives;
- workload impact;
- inclusion and exclusion rationale;
- risks;
- no automatic final investment decision.

### Methodology templates

- Equity;
- Credit;
- IB;
- Portfolio Monitoring;
- Sector Watch.

## 15. Rebuild both backlogs

Keep separate sections for:

### Evidence backlog

Include at least:

- packaged Coverage smoke test;
- runtime path verification;
- orphan inventory;
- current score fixture;
- query-count baseline;
- market-cap source inspection;
- current Excel integrity check.

### Implementation backlog

Include explicit tasks for:

- canonical market-cap selection;
- synthetic fallback removal;
- blocked/partial/complete scoring;
- holdings migration;
- BRL liquidity;
- canonical GICS scoring;
- hardcoded UI removal;
- delta containment;
- structured snapshots;
- snapshot hashing;
- archive-first;
- transactional hard delete;
- safe backup;
- orphan cleanup;
- connection-level foreign keys;
- capacity migration;
- active scenario invariant;
- Analyst Profile;
- owner management;
- scenario CRUD;
- source/freshness UI;
- N+1 optimization only after benchmark;
- Excel hardening;
- Work Queue event model.

For each task include:

- task ID;
- type;
- priority;
- complexity: S/M/L/XL;
- dependencies;
- parallelization;
- release blocker;
- evidence required;
- acceptance criteria.

Correct dependencies. For example, removing the synthetic fallback depends on score fixtures and market-cap source inspection, not database-path verification alone.

## 16. Expand the test matrix

The final test matrix must include:

### Scoring

- all factors available;
- each factor missing independently;
- several factors missing;
- complete, partial, and blocked states;
- sector as the only available factor;
- confirmed zero holding;
- unknown holding;
- not-applicable holding;
- stale holding;
- missing GICS;
- stale market cap;
- multiple presets;
- multiple tickers/share classes;
- deterministic market-cap selection;
- missing market history;
- daily BRL liquidity;
- weight renormalization;
- manual override;
- score clamping;
- methodology version.

### Snapshots

- material triggers only;
- no checklist-only snapshot;
- same score with different inputs creates a distinct snapshot;
- identical payload is deduplicated;
- baseline selection;
- delta after override;
- methodology-version change;
- non-comparable cross-version delta behavior;
- backward compatibility.

### SQLite and migration

- every orphan category;
- cleanup order;
- audit export or quarantine;
- backup creation;
- backup integrity;
- restore;
- migration twice;
- zero active scenarios;
- multiple active scenarios;
- active-scenario invariant;
- multiple SQLite connections;
- `PRAGMA foreign_key_check`;
- old database upgrade;
- rollback.

### Runtime paths

- desktop `--dev` using Documents;
- isolated `CVM_DATA_DIR`;
- `CVM_DB_DIR`;
- `SQLITE_PATH`;
- temporary test database;
- packaged path.

### Frontend

- typecheck;
- production build;
- complete/partial/blocked UI;
- source/freshness UI;
- owner editing;
- unassigned filter;
- scenario CRUD;
- scenario comparison;
- archive;
- Danger Zone;
- large-universe interaction.

### Performance

Measure before optimization:

- 10 companies;
- 100 companies;
- full or large universe;
- large market-history table;
- query count;
- cold and warm page load;
- Excel export time;
- memory.

### Packaged release

- clean install;
- update over the latest actually published release;
- existing database;
- database with orphans;
- offline mode;
- Coverage navigation;
- create/update/archive/delete;
- capacity page;
- owner management;
- Excel export;
- logs.

### Excel

- opens through `openpyxl`;
- no repair warning in Microsoft Excel;
- LibreOffice review when available;
- no merged cells;
- freeze panes;
- filters;
- expected sheets;
- source metadata;
- app-calculated values;
- optional formulas only as audit checks.

Do not hardcode a previous version such as `v0.26`. Determine the actual latest published release during implementation.

---

# Required phase structure

Use the following phases.

## Phase 0A — Reproduction and evidence

No behavior changes.

Must include:

- packaged smoke test;
- runtime paths;
- import graph;
- orphan inventory;
- score fixtures;
- market-cap source inspection;
- query-count baseline;
- current Excel validation;
- dev versus packaged comparison.

## Phase 0B — Immediate correctness and containment

Must include:

- canonical market-cap selection;
- synthetic fallback removal;
- complete/partial/blocked score policy;
- holdings unknown versus zero;
- BRL liquidity;
- canonical GICS identifier;
- removal of hardcoded peers/drivers;
- hide invalid delta;
- stop invalid snapshot writes;
- archive-first;
- transactional hard delete;
- regression tests.

## Phase 1 — Safe migrations and audit model

Must include:

- SQLite-safe backup;
- orphan export/cleanup;
- per-connection foreign keys;
- structured snapshots;
- payload-based deduplication;
- methodology versioning;
- holdings migration;
- capacity migration;
- active scenario invariant;
- Analyst Profile;
- rollback and upgrade tests.

## Phase 2 — Coverage workflow completion

Must include:

- canonical Capacity page;
- owner management;
- capacity by analyst and team;
- scenario CRUD and comparison;
- incremental company impact;
- source/freshness UI;
- missing-data UI;
- archive and Danger Zone;
- large-universe UX.

## Phase 3 — Excel hardening

Must include:

- Summary;
- Inputs & Methodology;
- Priority Rankings;
- Capacity;
- Work Queue snapshot;
- Decision History;
- Checks;
- app-calculated values;
- optional audit formulas;
- no merged cells;
- freeze panes;
- filters;
- integrity tests;
- repair validation.

## Phase 4 — Event-driven Work Queue

Must include:

- explicit event schema;
- local-first generation;
- CVM filings;
- stale deliverables;
- missing market data;
- relevant news;
- regulatory events;
- deduplication;
- acknowledgement;
- due dates;
- owners;
- offline cache;
- retention;
- reprocessing.

## Phase 5 — Future analytics and methodology templates

Must include:

- price correlation;
- benchmark-relative analysis;
- fundamental similarity;
- company relationships;
- peers and value chain;
- manager scenarios;
- methodology templates by analysis type.

---

# Required detail for every phase

Every phase must contain:

- Objective
- Scope
- Non-goals
- Likely files and modules
- Data-model impact
- UI impact
- Migration impact
- Dependencies
- Automated validation
- Manual validation
- Packaged validation
- Performance validation
- Risks
- Rollback strategy
- Acceptance criteria

Do not call the plan implementation-ready if these sections are missing.

---

# Required final document structure

1. Revision summary
2. Verified architecture and runtime paths
3. Corrected findings register
4. Financial data and scoring contract
5. SQLite integrity, backup, and migration plan
6. Revised phased implementation plan
7. Evidence backlog
8. Implementation backlog
9. Test and release matrix
10. Performance baseline plan
11. Documentation plan
12. Open decisions
13. Go/no-go recommendation

For every finding include:

- ID;
- severity;
- confidence;
- symptom;
- expected behavior;
- verified current behavior;
- evidence;
- root cause;
- financial/user risk;
- validation required;
- containing phase;
- final remediation phase.

---

# Acceptance criteria

The revised plan is acceptable only if:

1. No repository files were modified.
2. Packaged runtime remains unconfirmed until tested.
3. Market cap is selected deterministically per company.
4. Market caps are not summed across share classes without proof.
5. Liquidity is aggregated by ticker/day and then by company/day in BRL.
6. F04 is merged into liquidity if no independent use remains.
7. Score delta is described as invalid or missing, not as a crash.
8. Phase 0B contains archive-first and transactional permanent deletion.
9. Score status supports complete, partial, and blocked.
10. Holdings distinguish zero, unknown, not applicable, and stale.
11. Snapshot deduplication compares the complete payload.
12. Deltas across methodology versions are explicitly handled.
13. Orphan cleanup is defined per table.
14. Backup and restore are SQLite-safe.
15. Analyst Profile has one source of truth.
16. Phase 2 includes owner and scenario management.
17. Phase 4 contains a full event model.
18. Phase 5 separates price correlation and fundamental similarity.
19. Evidence and implementation backlogs are complete and correctly dependent.
20. The test matrix covers scoring, migration, runtime paths, UI, performance, packaged release, and Excel.
21. Every phase includes all required implementation-planning sections.
22. The latest actually published release is used for upgrade validation.
23. The final document fully replaces the previous plan.
24. The final document is safe for implementation approval.

---

After this prompt, paste or attach the current plan and end with:

> Return only the fully corrected replacement plan. Do not implement anything, modify files, create migrations, commits, issues, or pull requests. Do not include commentary outside the plan.
