---
name: cvmanalytics-vite-ui
description: Design, architecture, and quality contract for building the React/Vite/TS desktop frontend.
---

# CVMAnalytics Vite UI Skill Contract

This document defines the authoritative design, architecture, visual guidelines, and quality standards for building screens in the new React/Vite/TS desktop frontend (`apps/desktop-web`).

All AI agents and developers modifying or implementing screens in `apps/desktop-web/` **must** read and follow these rules.

---

## 1. Purpose & When to Use

Use this skill whenever you are:
- Planning, implementing, or modifying any UI component or route in `apps/desktop-web/`.
- Reviewing, refactoring, or evaluating the visual and functional quality of the Vite frontend.
- Adding API facades or data contracts to connect the React UI with the Python desktop bridge.

---

## 2. Project Context & Launch Modes

CVMAnalytics is a local-first Windows desktop financial data tool for Brazilian public companies.
- **Authoritative Runtime:** A packaged Windows executable (`dist/CVMAnalytics/CVMAnalytics.exe` built via `desktop/build_desktop.ps1`).
- **No Production Server:** The target architecture uses `pywebview` with a static Vite frontend, running without any bundled Node runtime or Next standalone server process.
- **Launch Modes:**
  - `CVMAnalytics.exe` $\rightarrow$ launches the Vite static UI (No Node process).
  - `CVMAnalytics.exe --vite` $\rightarrow$ alias of the default Vite static UI.
  - `CVMAnalytics.exe --legacy` $\rightarrow$ unsupported; warns, then continues into Vite.

---

## 3. Core Architecture Rules

To maintain separation of concerns and ensure the frontend works seamlessly in both desktop-frozen and browser-preview environments:

### The Bridge Pattern
All data access from React components must follow this unidirectional facade contract:
```
UI Component
  └──> src/lib/api/<facade>.ts (Frontend typed query facade)
        └──> src/lib/bridge/adapter.ts (Bridge mode router & mock/real dispatch)
              └──> window.pywebview.api (Dynamic global desktop bridge object)
                    └──> desktop/bridge.py (Python CVMBridge handler)
                          └──> Python Core (read_service / query_layer / SQLite)
```

### Strict Prohibitions
- **NO Direct Globals:** Never call `window.pywebview.api` directly from React UI components. Always use the typed facade files in `src/lib/api/` (e.g. `companies.ts`, `statements.ts`).
- **NO Direct SQLite:** Frontend code cannot issue SQL queries or communicate with SQLite directly. SQLite is entirely managed by the Python backend.
- **NO Hardcoded Filesystem Paths:** Never hardcode absolute or local filesystem paths (like `C:\Users\...` or `CVMAnalytics/...`) in frontend components. Use bridge methods (like `get_output_dir()`) to query paths dynamically from the backend.
- **NO Semantic Inflation:** Never invent, calculate, or alter financial data semantics on the frontend during migration. If the backend returns a certain data structure, preserve it exactly.
- **NO Next.js Work:** Do not create, restore, or modify Next.js routes, pages, API routes, or components. The old `apps/web` app was removed from the active tree. `desktop/node_portable` was removed in Phase 5B and must not be reintroduced.

---

## 4. Required Project Positioning

The CVMAnalytics Vite UI must look and feel like a **professional financial workstation terminal**:
- **What it IS:** Dense, readable, local-first, desktop-first, precise, fast, and trustworthy.
- **What it is NOT:** A generic SaaS dashboard, a consumer marketing page, a mobile-first responsive layout, or an over-animated crypto/fintech web app.
- **Not a Bloomberg Clone:** This app is not a Bloomberg clone. Do not copy Bloomberg branding, trademarks, proprietary UI, layout, exact colors, icons, keyboard shortcuts, or visual identity. Instead, draw inspiration from general financial-terminal principles: information density, workflow speed, absolute clarity, screen continuity, and deep analytical usability.

---

## 5. Design & Visual Direction

### Core Principles
1. **Data Before Decoration:** Prioritize company identity, period contexts, base coverage, and actual numbers. Avoid large empty headers, decorative drawings/illustrations, gratuitous gradients, and vague graphic panels.
2. **Dense but Readable:** Visual density is a feature for financial analysts. Support it with compact tables, clear groupings, proper alignment, tiny borders, and unambiguous unit representations.
3. **Familiarity Beats Novelty:** When porting a screen from the Next UI, keep the user's mental model, standard labels, and workflows. Focus on rendering data accurately before introducing new layout paradigms.
4. **Make Complexity Discoverable:** Present high-level summaries first, followed by filters, detailed tables, and finally deep-dive metrics or charts.
5. **Local-First Confidence:** Surface application status, data directory locations, database row counts, refresh times, and bridge status indicators clearly in the UI.

### Visual Tokens (CSS / Tailwind)
Tailwind configurations and custom styles should map to these core tokens:
- **App Canvas Background:** `--bg-app: #08090b;` (Dark, desk-black)
- **Panel Background:** `--bg-panel: #101216;` (Tonal charcoal layer)
- **Raised Panel Background:** `--bg-panel-raised: #151820;` (Dropdowns, overlays, popovers)
- **Muted Control Background:** `--bg-muted: #1b1f2a;` (Hover state, selected nav items)
- **Subtle Borders:** `--border-subtle: rgba(255, 255, 255, 0.08);` (Table dividers, quiet lines)
- **Strong Borders:** `--border-strong: rgba(255, 255, 255, 0.14);` (Active panels, dividers)
- **Primary Text:** `--text-primary: #f3f4f6;` (High-contrast numbers, labels)
- **Secondary Text:** `--text-secondary: #aeb4c0;` (Default body text)
- **Muted Text:** `--text-muted: #747b88;` (Explanations, metadata, headers)
- **Operational Accents:**
  - Regulatory Amber/Teal (Primary Focus): `--accent-primary: #f5a524;`
  - Info/Status: `--accent-info: #38bdf8;`
  - Audit Success: `--accent-success: #22c55e;`
  - Warning: `--accent-warning: #f59e0b;`
  - Error/Destructive: `--accent-danger: #ef4444;`

### Visual Rules
- **Scarcity of Color:** Do not color card backgrounds or tables with accent colors. Fills should be dark and neutral. Fills or borders with colors (red, green, blue) must be used strictly for functional status or semantic meaning.
- **Red/Green Accessibility:** Never rely solely on red/green colors to show a status (e.g. positive vs negative). Include text indicators, badges, or icons.
- **No Cyberpunk:** Avoid glowing neon borders, drop shadows, or heavy animations.

---

## 6. Typography

Typography must look clean, technical, and precise:
- **Preferred UI & Body Fonts:** Inter, Manrope, or system sans-serif.
- **Preferred Data Fonts:** IBM Plex Mono, JetBrains Mono, or system monospace.

### Typography Rules
- **Tabular Numbers:** Always use monospace fonts and `font-variant-numeric: tabular-nums;` for table columns, financial values, currency readouts, and KPIs to ensure column alignment.
- **Metadata Styling:** Use mono styling for stock tickers, CVM codes, dates, periods, and technical logs.
- **Weight and Contrast:** Avoid very thin font-weights (e.g., `< 400`) on dark backgrounds. They become unreadable due to subpixel rendering.
- **No Decorative Fonts:** Heading elements must be restrained and use clean display sans-serifs (like Space Grotesk or Manrope).

---

## 7. Layout & Navigation

- **Consistent Grid:** Use structured vertical and horizontal spacing.
- **Site Header & Navigation:** The top bar or sidebar should highlight the current active route, showing the status of the local database and the app version.
- **Breadcrumbs:** Use breadcrumbs for multi-level navigation (e.g., `Sectores > Energia > Petrobras`).
- **Entity Header:** Display the target company name, ticker, and CVM code prominently in a single layout at the top of detail screens.
- **NavTabs:** Use tabs for sub-views (e.g., "Visão Geral", "Demonstrativos", "Indicadores") to maintain context while switching sub-screens.

---

## 8. Tables & Cards

### Tables
- **Sticky Headers:** Always use sticky headers for data tables that scroll vertically.
- **Alignment:** Text columns must be left-aligned. Numeric financial columns must be right-aligned.
- **Borders & Hover:** Use thin `--border-subtle` separators and a subtle background change on hover (`--bg-muted`).
- **Units in Headers:** Financial columns must show the exact scale/currency in their header (e.g., `Receita (R$ mn)`, `Margem (%)`, `Alavancagem (x)`, `Variação (bps)`).
- **Missing Values:** Render missing values or empty cells as a clean em-dash (`—`). **Never** show raw `null`, `undefined`, `NaN`, or fallback `0` when data is missing.

### Cards
- **Tonal Separation:** Use tonal background changes (e.g., card background `--bg-panel` on app canvas `--bg-app`) and borders rather than heavy drop shadows.
- **Dense Grid:** Lay out cards in responsive grids, ensuring headers are distinct from values.

---

## 9. KPI Chart Panels

When displaying indicators and financial trends:
- **Lightweight Dependencies:** Inspect `package.json` before adding charting libraries. Prefer SVG/CSS sparklines or lightweight standard tools if available. Do not bundle heavy visualization suites unless justified.
- **Information over Decoration:** Charts must be readable in dark mode. Do not add random colored gradients under charts.
- **Units and Axes:** Every chart must explicitly label its Y-axis and X-axis with metrics, periods, and units (e.g., `Lucro Líquido (R$ milhões)`).
- **Handle Gaps:** Do not draw a continuous line over missing years. Show gaps or break lines where years have missing data.

---

## 10. Financial Semantics

- **Formulas:** When computing formulas on-the-fly (e.g., Margem EBITDA = EBITDA / Receita), document the exact formula in a tooltip or legend.
- **Divide by Zero:** Always check if denominators are zero or null to avoid displaying `Infinity` or `NaN`.
- **Misleading Precision:** Do not show financial values with excess decimals (e.g., R$ 1,234.56789). Use standard currency scale: raw numbers should round to 2 decimals for values, or 1 decimal/integer for millions.

---

## 11. Runtime & Bridge States

### Browser Preview Mode
When run directly in a browser (where `window.pywebview.api` is undefined), the UI must not crash. It should fall back to mock/local data and display a non-blocking diagnostic banner:
> ⚠️ **Browser preview mode.** Python bridge is not available. Open through the desktop shell to access local data.

### Desktop Mode
When run inside `pywebview`, show a subtle bridge status indicator in the status bar or header:
> `desktop · bridge ready`

### Bridge Failures
If a bridge call fails or times out:
- Do not crash the React app or show a white screen.
- Log the traceback to the browser console and capture the error message.
- Show a clear overlay or inline card explaining the failure (e.g., "Local database connection error").
- Keep navigation functional so the user can go to other screens or `/status` to run diagnostics.

---

## 12. Loading, Error, and Empty States

Every data panel or screen must support four fundamental states:
1. **Loading:** Use skeleton cards or line indicators matching the layout. Avoid general spinning wheels that cover the entire page.
2. **Error:** Be descriptive.
   - *Bad:* "Something went wrong."
   - *Good:* "Could not load company KPIs from the local database. Check if the database file is initialized in the status screen."
3. **Empty:** Give instructions to resolve.
   - *Bad:* "No data."
   - *Good:* "No financial statements found for this company. Run 'Atualizar Base' to download filings from CVM."
4. **Stale/Partial Data:** Warn if database indices are outdated.

---

## 13. Component Standards

Promote component reuse. Do not duplicate tabular views or cards across separate routes. Reusable component inventory:
- `PageHeader` $\rightarrow$ Standard header layout with breadcrumbs and title.
- `BridgeStatus` $\rightarrow$ Dynamic indicator showing mock/active bridge connectivity.
- `StatusBadge` $\rightarrow$ Standard styled badge for job status (idle, running, success, failed).
- `DataTable` $\rightarrow$ Reusable table wrapper with sticky headers, search, and sorting.
- `EmptyState` / `ErrorState` / `LoadingState` $\rightarrow$ Unifying empty, failed, and loader wrappers.
- `CompanyIdentity` $\rightarrow$ Combined corporate visual badge (ticker + CVM code).

---

## 14. Interaction & Performance UX

- **Focus Indicators:** Ensure all input boxes, chips, and filters have clear focus states (`outline-accent-primary`) for keyboard navigation.
- **Lag Prevention:** Debounce text search inputs (e.g., wait 300ms before querying suggestions). Avoid unnecessary state refreshes on scroll.
- **No Telemetry:** Never introduce Google Analytics, Sentry, or third-party web trackers into this offline-first desktop environment.

---

## 15. Screen Acceptance Checklist

A Vite UI screen is considered complete **only** if it passes all the following:
- [ ] **Browser Parity:** Works in standard browser preview using fallback/mock data.
- [ ] **Desktop Shell:** Launches and functions under `CVMAnalytics.exe`.
- [ ] **State Handling:** Covers loading, error, empty, and data-loaded states correctly.
- [ ] **Bridge Security:** Uses typed facades in `src/lib/api/` and never directly invokes `window.pywebview.api`.
- [ ] **Formatting:** Financial values display correct units, numbers use tabular-nums layout, missing values render as `—`.
- [ ] **No Traceback:** If an error occurs, it is caught gracefully without raw traceback in the main UI.
- [ ] **Typecheck:** Compiles with zero TypeScript errors (`npm run typecheck`).
- [ ] **Production Build:** Bundles successfully (`npm run build`).
- [ ] **No Bundled Node Runtime:** Packaged executable starts the Vite UI without spawning a bundled Node runtime or packaged legacy web server.
- [ ] **Data Safety:** Persistent user directories (`%USERPROFILE%\Documents\CVMAnalytics`) are preserved.

---

## 16. Output Expectations for AI Agents

When wrapping up a task, your final report **must** follow this format:

```markdown
### Phase [X] [Phase Name] Report

#### Initial Repo State
- Git status, commits inspected, and any pre-existing uncommitted files detected.

#### Feature Implemented
- Summary of what was created/modified.

#### Files Added
- [Link to added files]

#### Files Modified
- [Link to modified files]

#### Bridge Methods Used
- List of bridge functions called.

#### UI States Implemented
- Loading, error, empty, data rendering.

#### Local Validation
- TypeScript check and build logs.

#### packaged Validation
- Output of testing the frozen executable (Next vs Vite).

#### Existing Vite Screens Regression
- Smoke test check-ins (e.g., Companies, detail, update base, status screen).

#### What Still Uses Next
- Gaps still requiring legacy runtime.

#### Risks / Unknowns
- Potential bugs, environment requirements, or edge cases.
```

No agent should recreate the removed Next.js app or infer current UI architecture from historical migration docs. `apps/api` remains a FastAPI HTTP adapter, not the active frontend.
