# Final Correction Prompt — CVMAnalytics Coverage Universe Plan

You are performing the final correction pass on the existing:

**“CVMAnalytics Coverage Universe Hardening and Completion Plan”**

## Objective

Produce a complete, internally consistent, evidence-based replacement plan that is safe to approve for implementation.

This is a **PLAN-ONLY** task.

Do not:

- modify source code;
- modify tests;
- modify documentation;
- change schemas;
- create migrations;
- create commits;
- open issues or pull requests;
- implement any proposed phase.

Return only the corrected final plan.

## Repository rules

Before revising the plan, inspect the current repository state and follow:

- `AGENTS.md`
- `README.md`
- `docs/CONTEXT.md`
- `docs/active-project-map.md`
- `docs/reference/repository-map.md`
- `docs/dev-runtime-and-data-paths.md`
- `docs/release-process.md`
- `docs/skills/CVMANALYTICS_VITE_UI_SKILL.md`
- relevant ADRs under `docs/decisions/`

Confirm the real active runtime, entrypoints, database paths, imports, packaging flow, tables, queries, and tests before making claims.

Expected active frontend is `apps/desktop-web`, but verify it.

Do not inspect or plan changes against archived, removed, Next.js, prototype, or inactive application code.

## Main requirement

Correct all remaining issues listed below.

Every finding must include a confidence classification:

- Confirmed
- Probable
- Hypothesis
- Rejected

Do not present unexecuted runtime assumptions as facts.

---

# Mandatory corrections

## 1. Correct the PyInstaller finding

Do not state either:

- “Coverage definitely crashes in the packaged app”; or
- “Coverage definitely does not crash.”

The current static import graph includes Coverage-related modules, so absence from `hiddenimports` alone does not prove failure.

The corrected conclusion should be similar to:

> A packaged crash has not been reproduced. Static imports make the omission less likely to cause failure, but a packaged Coverage smoke test is still required.

Classify the finding based on actual evidence as:

- confirmed packaged failure;
- packaging hardening opportunity;
- unverified hypothesis;
- rejected finding.

Do not classify adding Coverage hidden imports as a P0 blocker unless the packaged failure is reproduced.

Required validation:

1. build the Vite frontend;
2. build the packaged executable;
3. launch it;
4. open Coverage;
5. list and create a universe;
6. add a company;
7. load prioritization;
8. export Excel;
9. inspect runtime logs.

## 2. Correct all database path descriptions

Do not simplify the development database path incorrectly.

Document separately:

### Packaged runtime

Expected default, subject to repository verification:

`%USERPROFILE%\Documents\CVMAnalytics\db\cvm_financials.db`

### Desktop `--dev`

The desktop development runtime may use the same Documents data root as the packaged application by default.

### Isolated development or tests

Document behavior under:

- `CVM_DATA_DIR`;
- `CVM_DB_DIR`;
- `SQLITE_PATH`;
- test fixtures and temporary databases;
- direct module execution, where relevant.

Include precedence order for path overrides.

## 3. Correct the foreign-key finding and risks

The confirmed issue is that SQLite foreign-key enforcement is not enabled on every connection.

Do not claim that this creates orphan rows during normal universe updates.

The main affected behavior is permanent deletion of parent rows when child rows rely on `ON DELETE CASCADE`.

Describe the real risks:

- orphaned Coverage rows;
- disconnected audit history;
- silent database growth;
- inconsistent future migrations;
- invalid referential state.

Do not claim duplicate primary keys unless reproduced.

## 4. Expand the orphan inventory and cleanup plan

Do not inspect only `universe_companies`.

The plan must inventory at least:

- `universe_companies` whose universe does not exist;
- `coverage_checklists` whose universe does not exist;
- `coverage_checklists` without a matching universe-company membership;
- `coverage_decision_history` whose universe does not exist;
- `coverage_capacity_scenarios` whose universe does not exist;
- future `coverage_score_snapshots` whose universe or company does not exist;
- Coverage rows referencing missing companies, where foreign keys require them.

For each orphan category, define:

- detection query;
- expected cardinality;
- cleanup rule;
- whether to delete, preserve, export, or quarantine;
- transaction boundary;
- rollback behavior.

Run or plan `PRAGMA foreign_key_check`.

## 5. Design a safe SQLite backup and restore procedure

Do not use a fixed backup filename.

Plan:

- timestamped backup filename;
- dedicated backup directory;
- free-space validation;
- WAL checkpoint where applicable;
- SQLite Backup API or database-closed consistent copy;
- backup integrity verification;
- metadata/log record;
- closure of active connections before restoration;
- handling of `.wal` and `.shm`;
- restore validation;
- rollback if migration verification fails.

Do not describe restoration as a simple rename while the application may still hold open connections.

## 6. Make missing GICS a missing factor

Do not default missing GICS to a sector score of `50.0`.

Required behavior:

```text
sector_score = null
missing_factors includes "sector_complexity"
score_status = "partial" or "blocked"
```

Apply the same explicit missing-data policy used by other score factors.

Use a canonical stable identifier, such as:

- `gics_sector_slug`;
- internal enum;
- canonical code.

Do not depend on display labels alone.

Do not infer GICS from ticker, CVM sector, or company name.

## 7. Distinguish zero holdings from unknown holdings

The revised plan must explicitly separate:

- confirmed 0% holding;
- holding not informed;
- universe that does not represent a portfolio;
- stale holding information;
- manually entered value;
- imported portfolio value.

Evaluate a contract such as:

```text
holding_pct
holding_status
holding_source
holding_as_of_date
```

Do not allow an unknown holding to silently become a valid zero-score input.

Define how Equity, Credit, IB, Sector Watch, and Portfolio Monitoring universes should treat the holding factor.

## 8. Define the canonical market-cap source

The current query may select an arbitrary row from `company_universe` using `LIMIT 1`.

The plan must define:

- canonical preset;
- active universe preset, if applicable;
- source priority;
- latest valid source date;
- currency;
- cache timestamp;
- stale threshold;
- multiple ticker handling;
- multiple share-class handling;
- missing market-cap behavior;
- conflict resolution when multiple rows exist.

Do not use an unordered `LIMIT 1`.

## 9. Merge the latest-price issue into the liquidity design

After removing the synthetic market-cap fallback, latest price may no longer be needed for market-cap scoring.

Do not keep a separate release blocker merely to fix an unused price query.

Treat price as part of the liquidity definition.

Define the intended metric, for example:

```text
daily_traded_value_brl = share_volume × raw_close_brl
```

Document:

- `close` versus `adjusted_close`;
- why the selected field is correct;
- daily aggregation;
- lookback period;
- minimum number of observations;
- missing trading days;
- ticker changes;
- splits and corporate actions;
- stale data;
- source and timestamp.

## 10. Correct the score-delta severity

Do not claim the invalid snapshot conversion crashes checklist actions unless reproduced.

The current behavior likely catches conversion errors and returns no delta.

Describe the real impact:

- missing delta;
- incorrect baseline;
- semantically invalid snapshot records;
- misleading trend display;
- lack of auditability.

Since score delta is currently unsafe, Phase 0B must include an immediate containment action:

- hide or disable the delta;
- stop writing invalid score snapshot events;
- add regression tests.

The structured snapshot model may be implemented later in Phase 1.

## 11. Define score snapshot triggers

Do not create snapshots on every page load or every read calculation.

Define material triggers such as:

- scoring-weight changes;
- manual override changes;
- manually entered factor changes;
- market-cap refresh;
- market-history refresh;
- methodology-version change;
- explicit user snapshot;
- tier change only if tier affects the formula.

Checklist changes must not generate score snapshots unless checklist completion participates in the formula.

Define:

- idempotency;
- deduplication;
- previous-baseline selection;
- retention;
- ordering;
- formula and methodology version.

## 12. Correct capacity source precedence

After migration, source precedence must be:

```text
active capacity scenario
→ legacy assumptions_json during compatibility window
→ defaults
```

Do not design code paths that continue reading legacy assumptions before the active scenario.

The plan must cover:

- exactly one active scenario per universe;
- behavior if zero active scenarios exist;
- behavior if multiple active scenarios exist;
- default scenario creation;
- idempotent migration;
- migration marker/version;
- preservation of existing values;
- scenario naming;
- active scenario switching;
- temporary backward-compatible reads;
- eventual legacy-field retirement.

## 13. Stage foreign-key enforcement safely

Do not mix “startup PRAGMA” with “every connection enforcement.”

`PRAGMA foreign_keys = ON` must be applied to each new SQLite connection.

Recommend a staged strategy:

### Stage A

Implement explicit Coverage-specific transactional deletion and archive-first UX.

### Stage B

Create a verified backup and inventory/clean existing orphans.

### Stage C

Enable foreign keys through the canonical SQLAlchemy connection mechanism for every SQLite connection.

### Stage D

Run:

- migration tests;
- multi-connection tests;
- upgrade tests;
- `PRAGMA foreign_key_check`;
- packaged-runtime tests.

Explain whether explicit transactional deletion remains as defensive redundancy.

## 14. Complete the Analyst Profile scope

Do not describe Analyst Profile as only a backend table or Python setting.

The plan must decide whether it belongs in:

- application settings storage;
- the financial database;
- a dedicated local profile file;
- another existing settings mechanism.

Cover:

- Settings UI;
- bridge methods;
- TypeScript contracts;
- validation;
- editing;
- persistence;
- stable local ID;
- display name or alias;
- optional team/role;
- privacy;
- unknown-profile fallback;
- audit-history integration;
- migration behavior.

Operating-system username may be suggested during setup but must not be treated as verified identity.

## 15. Complete Phase 2 scope

Phase 2 must explicitly include:

- owner assignment and editing;
- unassigned-company state;
- owner filters;
- capacity by analyst;
- capacity by team;
- active scenario selection;
- scenario creation;
- scenario duplication;
- scenario comparison;
- scenario deletion/archive rules;
- incremental impact of adding a company;
- archive-first universe workflow;
- permanent deletion in a secondary Danger Zone;
- large-universe filters;
- table virtualization when measurement justifies it;
- loading, empty, missing-data, and error states;
- source and freshness disclosure.

Capacity by analyst is not complete until `owner_analyst` can be maintained through the UI.

## 16. Remove reliance on Excel cached formulas

Do not propose manually writing cached Excel formula results as a required design.

`openpyxl` does not calculate formulas.

The workbook must remain useful and auditable without recalculation.

Recommended model:

- export validated values calculated by the application;
- export raw inputs;
- export normalized factor values;
- export weights;
- export factor contributions;
- export calculated score;
- export override;
- export final score;
- export missing-data flags;
- export sources and timestamps;
- export formula text and methodology version.

Optional Excel formulas may be included as independent audit checks, but they must not be the only source of the displayed result.

Excel rules:

- no merged cells;
- freeze panes;
- logical filters;
- standardized dates and units;
- negatives in parentheses;
- zeros as `-`;
- workbook opens without repair.

## 17. Define the event-driven Work Queue architecture

Do not use vague phrases such as “worker hooks listen for events.”

Design a local-first event generation model.

Evaluate event creation during:

- CVM refresh;
- market-data refresh;
- news import;
- manual reconciliation;
- startup reconciliation only when bounded and necessary.

The model must include:

- event ID;
- universe ID;
- company ID;
- source type;
- source reference;
- event timestamp;
- detection timestamp;
- due date;
- severity;
- status;
- acknowledgement;
- owner;
- resolution;
- deduplication key;
- source timestamp;
- created/updated timestamps.

Plan:

- idempotent event generation;
- bounded reconciliation;
- offline behavior;
- local cache;
- retention;
- reprocessing;
- error logs;
- no repeated external calls;
- no continuous background polling without demonstrated need.

Define “news anomaly” objectively or remove it from the near-term scope.

## 18. Restore a complete Phase 5

Phase 5 must be explicitly present and include future analytics:

- return correlation;
- benchmark-relative correlation;
- selectable periods;
- clusters;
- duplicated market exposure;
- fundamental similarity;
- real peers;
- competitors;
- suppliers;
- customers;
- subsidiaries;
- commodities;
- FX;
- rates;
- regulation;
- concessions;
- utilities-specific drivers;
- source and confidence for relationships;
- manager recommendation scenarios;
- methodology templates for:
  - Equity;
  - Credit;
  - IB;
  - Portfolio Monitoring;
  - Sector Watch.

Clearly separate price correlation from fundamental similarity.

## 19. Rebuild the backlog

Separate the backlog into:

### Evidence tasks

Examples:

- packaged Coverage smoke test;
- orphan inventory;
- query-count baseline;
- current score fixture capture;
- database-path verification.

### Implementation tasks

Include explicit tasks for:

- removing synthetic market cap;
- implementing the missing-data contract;
- selecting canonical market-cap rows;
- correcting BRL liquidity;
- canonical GICS sector complexity;
- removing hardcoded peers/drivers;
- containing invalid score delta;
- creating structured snapshots;
- protecting deletion;
- cleaning orphans;
- enabling connection-level foreign keys;
- migrating capacity settings;
- scenario CRUD;
- Analyst Profile;
- owner management;
- performance optimization only after measurement;
- archive-first workflow;
- Excel hardening;
- event-driven Work Queue.

Do not keep packaging hidden imports as a P0 task unless runtime failure is reproduced.

For each backlog item provide:

- task ID;
- type: evidence or implementation;
- priority;
- complexity: S/M/L/XL;
- dependencies;
- parallelization potential;
- release blocker;
- evidence required before implementation;
- acceptance criteria.

Do not give calendar estimates.

## 20. Expand the test matrix

Include tests for:

### Scoring

- all factors available;
- each factor missing independently;
- multiple factors missing;
- holding confirmed at 0%;
- holding unknown;
- stale holding;
- missing GICS;
- stale market cap;
- multiple market-cap presets;
- multiple share classes;
- invalid or missing market history;
- correct BRL liquidity;
- explicit weight renormalization;
- completeness metadata;
- manual override;
- score clamping;
- methodology version.

### Snapshots

- snapshot only on material events;
- no snapshot on checklist-only changes;
- correct baseline selection;
- delta after override;
- delta after methodology change;
- duplicate trigger idempotency;
- backward compatibility with old history.

### SQLite and migration

- orphan detection for every Coverage table;
- cleanup order;
- backup creation;
- backup integrity;
- restore procedure;
- migration executed twice;
- zero active scenarios;
- multiple active scenarios;
- one active scenario invariant;
- foreign keys across multiple connections;
- `foreign_key_check`;
- old database upgrade;
- rollback.

### Runtime paths

- desktop dev using Documents;
- isolated dev using `CVM_DATA_DIR`;
- `SQLITE_PATH` override;
- test temporary database;
- packaged data root.

### Performance

Measure before optimizing:

- 10 companies;
- 100 companies;
- large/full universe;
- large market-history table;
- query count;
- page-load time;
- cold versus warm load;
- Excel export time;
- memory impact.

### Frontend

- typecheck;
- production build;
- missing-data UI;
- loading;
- empty;
- error;
- owner editing;
- capacity scenarios;
- archive and Danger Zone flows;
- large-universe interaction.

### Packaged release

- clean install;
- update over the latest actually published release;
- existing database;
- existing database with orphans;
- offline mode;
- Coverage navigation;
- create/update/archive/delete workflow;
- Excel export.

### Excel

- open with `openpyxl`;
- no repair warning in Microsoft Excel;
- review in LibreOffice where available;
- no merged cells;
- freeze panes;
- filters;
- expected sheets;
- source metadata;
- formulas, if included, are optional checks only.

Do not hardcode an assumed previous release version. Determine the latest published release during implementation.

---

# Required final phase structure

The corrected plan must use this structure.

## Phase 0A — Reproduction and evidence

No behavior changes.

Include:

- import graph;
- packaged Coverage smoke test;
- runtime path verification;
- orphan inventory;
- score fixture capture;
- query-count baseline;
- dev versus packaged comparison;
- current Excel validation.

## Phase 0B — Immediate correctness and containment

Include:

- remove synthetic market cap;
- canonical market-cap selection;
- explicit missing-data policy;
- correct BRL liquidity;
- canonical GICS identifier;
- holding unknown versus zero;
- remove hardcoded peers/drivers;
- hide or disable invalid score delta;
- stop invalid snapshot writes;
- archive-first UI;
- transactional permanent deletion;
- regression tests.

## Phase 1 — Safe migrations and audit model

Include:

- backup;
- orphan cleanup;
- connection-level foreign keys;
- structured score snapshots;
- methodology versioning;
- capacity migration;
- active scenario invariant;
- Analyst Profile;
- rollback and migration tests.

## Phase 2 — Coverage workflow completion

Include:

- canonical Capacity page;
- `/coverage/capacity`;
- scenario CRUD and comparison;
- owner management;
- capacity by analyst/team;
- incremental company impact;
- source/freshness UI;
- missing-data UX;
- archive and Danger Zone;
- large-universe UX.

## Phase 3 — Excel hardening

Include:

- Summary;
- Inputs & Methodology;
- Priority Rankings;
- Capacity;
- Work Queue snapshot;
- Decision History;
- Checks;
- values calculated by the app;
- optional audit formulas;
- no merged cells;
- freeze panes;
- filters;
- integrity and repair tests.

## Phase 4 — Event-driven Work Queue

Include:

- explicit event schema;
- filings;
- stale deliverables;
- missing market data;
- relevant news;
- regulatory events;
- idempotent generation;
- deduplication;
- acknowledgement;
- due dates;
- ownership;
- offline cache;
- retention and reprocessing.

## Phase 5 — Future analytics and methodology templates

Include:

- correlation;
- benchmark comparison;
- fundamental similarity;
- company relationships;
- peers;
- value chain;
- manager scenarios;
- templates by analysis type.

---

# Required final output format

## 1. Revision summary

List:

- retained findings;
- corrected findings;
- rejected findings;
- unverified hypotheses;
- newly identified gaps.

## 2. Verified architecture and runtime paths

Include:

- active frontend;
- pywebview bridge;
- Python service;
- SQLite tables;
- packaged runtime;
- desktop development runtime;
- isolated development and tests;
- environment overrides;
- Excel flow.

## 3. Corrected findings register

For every finding:

- ID;
- severity;
- confidence;
- symptom;
- expected behavior;
- verified current behavior;
- evidence;
- root cause;
- user and financial risk;
- validation required;
- phase where it is addressed.

## 4. Financial data and scoring contract

Define:

- market cap;
- liquidity;
- holdings;
- sector complexity;
- missing-data policy;
- weight renormalization;
- manual overrides;
- score status;
- completeness;
- methodology version;
- source metadata;
- snapshot triggers;
- delta behavior.

## 5. SQLite integrity, backup, and migration plan

Include:

- backup;
- orphan inventory;
- cleanup;
- transactional deletion;
- connection-level FK enforcement;
- capacity migration;
- snapshot migration;
- compatibility window;
- rollback.

## 6. Revised phased implementation plan

For every phase:

- objective;
- scope;
- non-goals;
- likely files/modules;
- data-model impact;
- UI impact;
- migration impact;
- dependencies;
- validation;
- packaged validation;
- risks;
- rollback;
- acceptance criteria.

## 7. Evidence backlog

## 8. Implementation backlog

## 9. Test and release matrix

## 10. Performance baseline plan

## 11. Documentation plan

Do not add Coverage methodology details to `AGENTS.md`.

Prefer:

- `docs/reference/coverage-methodology.md`;
- GICS reference documentation;
- migration documentation;
- release notes;
- packaged validation evidence.

## 12. Open decisions

Only include decisions that materially affect:

- financial correctness;
- schema;
- migration safety;
- architecture;
- UX;
- privacy;
- release safety.

For each:

- options;
- trade-offs;
- recommendation;
- safe default.

## 13. Go/no-go recommendation

Separate:

- confirmed blockers;
- hypotheses requiring reproduction;
- containment needed before release;
- work safe to defer;
- minimum safe next-release scope.

---

# Acceptance criteria

The revised plan is acceptable only if:

1. No files were modified.
2. Runtime claims are classified by confidence.
3. Packaged failure is not asserted without reproduction.
4. Database paths and override precedence are correct.
5. Foreign-key risks and orphan cleanup cover every Coverage table.
6. Backup and restore are SQLite-safe.
7. Missing GICS is not silently assigned a default score.
8. Unknown holdings are distinct from confirmed zero holdings.
9. Market-cap row selection is deterministic and auditable.
10. Liquidity is defined in BRL with correct units.
11. Invalid score delta is contained in Phase 0B.
12. Structured snapshots use material triggers only.
13. Capacity migration uses active scenario as canonical source.
14. Analyst Profile includes UI, bridge, persistence, privacy, and fallback.
15. Phase 2 contains owner and scenario management.
16. Excel does not depend on formula caches.
17. Work Queue has an explicit local-first event model.
18. Phase 5 is present.
19. Evidence and implementation backlogs are separate.
20. The test matrix covers clean install, upgrade, offline, migration, performance, packaged runtime, and Excel repair.
21. The final document completely replaces the previous plan.
22. The final document is ready for implementation approval.

---

After this prompt, paste the current plan and end with:

> Return only the fully corrected replacement plan. Do not include code patches, implementation changes, or commentary outside the plan.
