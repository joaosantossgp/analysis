# Company On-Demand Source Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let analysts choose whether the company `Update data` action refreshes CVM financial data, market data, or both.

**Architecture:** Keep the preference in browser local storage because it is a user-interface preference rather than financial data. `CompanyCommandBar` owns the selection, uses the existing CVM mutation and market-history mutation independently, and exposes the choices in the existing on-demand range popover.

**Tech Stack:** React, TypeScript, TanStack Query, Vitest.

## Global Constraints

- New UI copy is English-only.
- Both update sources are selected by default.
- Download history remains CVM-only and says so in the popover.
- Market data continues to fetch complete provider history; no date-range setting is introduced.
- No market-cap fetch is reintroduced.

---

### Task 1: Test and implement source preference behavior

**Files:**
- Modify: `apps/desktop-web/src/components/CompanyCommandBar.tsx`
- Modify: `apps/desktop-web/src/components/CompanyCommandBar.test.ts`

**Interfaces:**
- Produces `loadOnDemandUpdateSources`, `saveOnDemandUpdateSources`, and a selected-source `Update data` action.
- Consumes existing `requestCompanyRefresh` and `triggerAllMarketHistoryRefresh` operations.

- [ ] **Step 1: Write failing tests**

```ts
expect(loadOnDemandUpdateSources(null)).toEqual({ cvm: true, market: true });
expect(updateSourcesEnabled({ cvm: false, market: false })).toBe(false);
```

- [ ] **Step 2: Run the focused test**

Run: `npm --prefix apps/desktop-web run test -- CompanyCommandBar.test.ts`

Expected: FAIL because the preference helpers do not exist.

- [ ] **Step 3: Add the minimal preference helpers and source-gated action**

```ts
function updateCompanyData() {
  if (updateSources.cvm) refreshMutation.mutate({ type: "incremental" });
  if (updateSources.market) marketRefreshMutation.mutate();
}
```

- [ ] **Step 4: Render source checkboxes in `HistoryRangePopover`**

```tsx
<Checkbox label="CVM financial data" checked={sources.cvm} onChange={...} />
<Checkbox label="Market data" checked={sources.market} onChange={...} />
<p>Download history retrieves CVM financial data only.</p>
```

- [ ] **Step 5: Verify focused tests and typecheck**

Run: `npm --prefix apps/desktop-web run test -- CompanyCommandBar.test.ts; npm --prefix apps/desktop-web run typecheck`

Expected: PASS.

### Task 2: Verify the on-demand interaction visually

**Files:**
- Verify: `apps/desktop-web/src/components/CompanyCommandBar.tsx`

- [ ] **Step 1: Run the Vite mock application and open a company workspace**

Run: `npm --prefix apps/desktop-web run dev:mock -- --port 5184`

- [ ] **Step 2: Use Playwright to open the Download history settings control**

Confirm both checkboxes are selected, the CVM-only download note is visible, and the popover does not expand the card layout.

- [ ] **Step 3: Toggle one source and click Update data**

Confirm only the selected source starts and the chart refresh notice remains a transient popover.
