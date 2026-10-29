# Company Chart Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify the two company chart headers and enable market metrics with at most two chart units.

**Architecture:** Keep market selection and unit validation in `lib/marketHistory/series.ts`; the persisted hook owns the selected metric list and a compatible chart type. The two panel components only render those choices using existing compact controls.

**Tech Stack:** React 19, TypeScript, Vitest, Vite, Playwright.

## Global Constraints

- New UI copy is English-only.
- Use existing UI controls and chart dependencies; add no dependency.
- Preserve explicit loading, empty, stale, and error states.
- Allow no more than two distinct market units in one chart.

---

### Task 1: Model multi-metric market selection

**Files:**
- Modify: `apps/desktop-web/src/lib/marketHistory/series.ts`
- Modify: `apps/desktop-web/src/lib/marketHistory/useMarketHistoryConfig.ts`
- Test: `apps/desktop-web/src/lib/marketHistory/series.test.ts`

- [ ] Write failing tests for a valid BRL-plus-percent selection and a rejected third unit.
- [ ] Implement unit-aware metric selection helpers and multi-metric series construction.
- [ ] Migrate persisted single-view configuration to a selected-metric list and normalize the shared chart type.
- [ ] Run `npm --prefix apps/desktop-web run test -- src/lib/marketHistory/series.test.ts`.

### Task 2: Render concise company chart controls

**Files:**
- Modify: `apps/desktop-web/src/components/MarketHistoryPanel.tsx`
- Modify: `apps/desktop-web/src/components/indicators/IndicatorControls.tsx`
- Modify: `apps/desktop-web/src/routes/CompanyDetailPage.tsx`
- Test: `apps/desktop-web/src/routes/__tests__/CompanyDetailPage.test.ts`

- [ ] Write failing tests for title case and the updated control labels.
- [ ] Replace Market View with the multi-metric picker and render Frequency with `PeriodSelect`.
- [ ] Remove normal-state source/methodology subtitles while retaining state-specific copy.
- [ ] Run the focused component test.

### Task 3: Verify the analyst workflow

**Files:**
- Validate: `apps/desktop-web/src/components/MarketHistoryPanel.tsx`
- Validate: `apps/desktop-web/src/routes/CompanyDetailPage.tsx`

- [ ] Run frontend tests, `typecheck`, and `build`.
- [ ] Start mock Vite on a dedicated port and use Playwright to verify Price plus Dividend Yield, title hierarchy, and the Frequency select at normal desktop width.
