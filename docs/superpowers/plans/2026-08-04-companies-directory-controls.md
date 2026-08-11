# Companies Directory Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Companies directory controls quieter and provide correct server-side table sorting.

**Architecture:** The Vite component stores the selected column and direction in URL parameters and sends them through the typed companies facade. The bridge validates the values and the read service/query layer applies the resulting order before pagination for market-cap snapshots, the local catalog, and SQL fallback paths.

**Tech Stack:** React, TypeScript, TanStack Query, React Router, Python, SQLAlchemy, Vitest, pytest.

## Global Constraints

- Preserve the pywebview bridge facade; no direct bridge calls from React components.
- Keep new user-facing Vite strings in English.
- Missing values must remain visible and sort last.
- Do not alter company data, source provenance, or storage.

---

### Task 1: Define and test the sorting contract

**Files:**
- Modify: `apps/desktop-web/src/components/CompaniesTable.test.ts`
- Modify: `apps/desktop-web/src/components/CompaniesTable.tsx`
- Modify: `apps/desktop-web/src/lib/bridge/types.ts`

**Interfaces:**
- Produces `CompanyDirectorySortKey` and `CompanyDirectorySortDirection` for frontend query state.
- Produces a tested column metadata contract including each sortable key.

- [ ] **Step 1: Write failing frontend tests**

Add assertions that all directory columns expose a sortable key and that the UI helper toggles an initial column to `asc`, then to `desc`.

- [ ] **Step 2: Run the focused frontend test**

Run: `npm --prefix apps/desktop-web run test -- CompaniesTable.test.ts`

Expected: FAIL because no sort metadata/helper exists.

- [ ] **Step 3: Add minimal TypeScript types and helper**

Define the allowlisted keys for `company`, `ticker`, `sector`, `industryGroup`, `marketCap`, `data`, `years`, and `cvm`, and a pure toggle helper.

- [ ] **Step 4: Re-run the focused frontend test**

Run: `npm --prefix apps/desktop-web run test -- CompaniesTable.test.ts`

Expected: PASS.

### Task 2: Propagate and test desktop sorting

**Files:**
- Modify: `desktop/bridge_api/companies.py`
- Modify: `src/financials/read_service_query.py`
- Modify: `src/financials/query_layer.py`
- Test: relevant existing Python companies/read-service tests, or a focused new test beside them.

**Interfaces:**
- Consumes `sort_by: str | None` and `sort_direction: str | None` from `get_companies`.
- Produces a `CompanyDirectoryPage` whose items are sorted before pagination.

- [ ] **Step 1: Write failing Python tests**

Test that a text sort returns the complete filtered result A–Z before page slicing, a second request reverses it, and missing numeric values remain last.

- [ ] **Step 2: Run the focused Python test**

Run: `pytest tests/ -k companies --maxfail=1`

Expected: FAIL because sort parameters are not accepted.

- [ ] **Step 3: Implement an allowlisted sort specification**

Pass validated values from the bridge to the service. Apply the mapping in snapshot, catalog, local SQL, and fallback paths; do not interpolate untrusted column values in SQL.

- [ ] **Step 4: Re-run focused Python tests**

Run: `pytest tests/ -k companies --maxfail=1`

Expected: PASS.

### Task 3: Update the Companies table controls

**Files:**
- Modify: `apps/desktop-web/src/components/CompaniesTable.tsx`
- Test: `apps/desktop-web/src/components/CompaniesTable.test.ts`

**Interfaces:**
- Consumes the sort URL state and typed API query properties from Tasks 1–2.
- Produces accessible clickable column headers and a compact filter bar.

- [ ] **Step 1: Write failing UI contract tests**

Assert that the legacy labels/banner are absent, search has an accessible name and icon, and the active sort header exposes `aria-sort`.

- [ ] **Step 2: Run focused UI tests**

Run: `npm --prefix apps/desktop-web run test -- CompaniesTable.test.ts`

Expected: FAIL because the legacy markup remains.

- [ ] **Step 3: Implement the minimal UI change**

Remove labels/banner, position a non-interactive magnifier in the input, and render table header buttons with arrows only for the selected column.

- [ ] **Step 4: Re-run focused UI tests**

Run: `npm --prefix apps/desktop-web run test -- CompaniesTable.test.ts`

Expected: PASS.

### Task 4: Validate integration

**Files:**
- Modify only files from Tasks 1–3 if a validation failure requires it.

- [ ] **Step 1: Run frontend validation**

Run: `npm --prefix apps/desktop-web run typecheck`, then `npm --prefix apps/desktop-web run test`, then `npm --prefix apps/desktop-web run build`.

- [ ] **Step 2: Run Python validation**

Run: `pytest tests/ -k companies --maxfail=1`.

- [ ] **Step 3: Verify in Dev mode**

Open Companies, click a text and a numeric header twice each, confirm the arrow direction/rows change, then search and confirm sorting remains correct across pages.
