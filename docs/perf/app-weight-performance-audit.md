# App Weight & Performance Audit Report

Date: 2026-05-19
Scope: read-only investigation plus this report file. No application source, build script, dependency, data, or runtime behavior was changed.

## 0. Product Decisions Recorded After Audit

The following decisions were provided after the first audit report and should guide the next implementation phase:

| Question | Decision |
|---|---|
| Acceptable installed folder size | Current multi-GB package is acceptable for now. Package-size reduction is useful, but not a blocker. |
| `/design-system` | Keep available. Treat as a maintained internal/product-support surface. |
| `/design-system` visibility | Keep visible in navigation/footer. |
| `/demo-analysis` | Delete in a future implementation pass. |
| `/portfolio` | Delete in a future implementation pass. |
| Deleted route documentation | Remove `/demo-analysis` and `/portfolio` entirely from product documentation; do not keep archived screenshots/docs. |
| "Em breve" navigation items | Keep visible before the features exist. |
| Desktop theme default | Follow Windows system theme. Do not force dark mode globally. |
| `/atualizar-base` audience | Every user should be able to access it. Do not treat it as admin-only. |
| Target performance machine | Average to low-end Windows laptop. Optimize perceived speed and responsiveness for that class. |

## 0.1 Implementation Pass Update

Implemented on 2026-05-19:

| Area | Result |
|---|---|
| Company detail contract | Fixed `CompanyInfoDTO` / API payload mismatch for `sector_name` and `sector_slug`. |
| Suggestions contract | Restored `/companies/suggestions` to the minimal payload expected by API tests. |
| Removed routes | Deleted `/demo-analysis` and `/portfolio`; removed `Portfolio` from header/footer. |
| Kept route | `/design-system` remains visible in header/footer. |
| React lint | Fixed the render-hygiene lint errors around synchronous state updates in effects and stale effect dependencies. |
| E2E | Updated stale assertions to current UI/data and made the sector hub test tolerate one controlled cold-start retry. |
| Perf guardrail fixture | Updated stale sector fixture from `/sectors/energia` to `/sectors/energy` and seeded synthetic GICS fields. |

Current validation after this pass:

| Check | Result |
|---|---|
| `npm run lint` | Passed |
| `npm run typecheck` | Passed |
| `npm run test:unit` | Passed, 122 tests |
| `npm run test:e2e` | Passed, 10 tests |
| `pytest apps/api/tests -q` | Passed, 121 tests |
| `pytest tests -q` | Passed, 158 tests |
| `python scripts/benchmark_read_paths.py --runs 10` | Passed |
| `python scripts/perf_guardrail.py check --baseline docs/perf/performance_baseline.json` | Failed on real budgets, not broken fixtures |

Updated measurements after route deletion:

| Metric | Current |
|---|---:|
| `apps/web/.next/static` | 2.27 MB |
| `apps/web/.next/standalone` | 18.43 MB |
| `apps/web/public` | 12.78 MB |
| `dist/CVMAnalytics` | 3879.67 MB |
| `dist/CVMAnalytics/data/input` | 3654.09 MB |
| `dist/CVMAnalytics/data/db` | 138.68 MB |

Current route JS diagnostics:

| Route | First-load JS | Chunks | Status |
|---|---:|---:|---|
| `/design-system` | 1,005,802 B | 18 | Kept visible by product decision |
| `/empresas/[cd_cvm]` | 900,913 B | 20 | Still over guardrail max 806,500 B |
| `/empresas` | 847,645 B | 17 | Passes narrowly |
| `/atualizar-base` | 737,560 B | 16 | No explicit guardrail |
| `/setores/[slug]` | 734,597 B | 16 | Passes narrowly |
| `/setores/[slug]/[sub_slug]` | 734,597 B | 16 | No explicit guardrail |
| `/` | 692,022 B | 14 | Passes |
| `/setores` | 688,974 B | 15 | Passes |

Remaining measured performance findings:

1. `/empresas/[cd_cvm]` still exceeds the first-load JS budget by about 94 KB.
2. `GET /sectors/energy` now resolves correctly in the guardrail but exceeds the old legacy-sector API budget: median 173.91 ms vs 118.0 ms, p95 229.89 ms vs 130.68 ms.
3. Playwright server logs still show real slow paths, especially `get_company_years_map` around 2.5 s in the latest full e2e run.
4. Unit tests still emit Node module-type reparsing warnings; this is developer-experience overhead, not runtime product behavior.

## 1. Executive Summary

The app is not mainly heavy because of the executable. The packaged folder is heavy because `dist/CVMAnalytics/data/input` contains about 3.65 GB of raw and processed CSV data. The executable itself is about 19.52 MB, the standalone web bundle is about 21.45 MB, and SQLite is about 124 MB in the packaged app.

The most urgent product blocker found during the audit is not a pure performance issue: the company detail API contract is currently broken around `sector_name` and `sector_slug`. This makes company detail screens show unavailable states in browser and e2e runs, which prevents reliable measurement of the most important analysis route.

The web bundle is close to or above the existing route budgets. `/empresas/[cd_cvm]` is over budget at about 905 KB first-load JS against a max budget of 806 KB. `/empresas` and `/setores/[slug]` pass but are near their ceilings. Internal/demo routes are also large: `/design-system` is about 1.01 MB and `/demo-analysis` is about 948 KB.

The UI is visually ambitious and mostly coherent, especially the company directory and operational update screen. The main visual risk found is not "too polished"; it is inconsistent theme/readability. In the sampled dev run, the app rendered in light theme while the product direction is dark "Audit Desk", and the home Remotion feature panel had low-contrast white text on a pale surface.

## 2. Evidence Collected

### Environment

| Item | Value |
|---|---:|
| Git branch | `main` |
| Git commit | `9b08760` |
| Node | `v24.14.1` |
| npm | `11.11.0` |
| Python | `3.11.9` |
| Product target | `dist/CVMAnalytics/CVMAnalytics.exe` |

### Package and Storage Size

| Path | Size | Files | Interpretation |
|---|---:|---:|---|
| `dist/CVMAnalytics` | 3879.67 MB | 3099 | Current packaged desktop folder |
| `dist/CVMAnalytics/data` | 3792.77 MB | 172 | Dominates package size |
| `dist/CVMAnalytics/data/input` | 3654.09 MB | 168 | Largest weight source |
| `dist/CVMAnalytics/data/input/processed` | 3316.39 MB | 147 | Main package bloat candidate |
| `dist/CVMAnalytics/data/input/raw` | 337.70 MB | 21 | Secondary package bloat candidate |
| `dist/CVMAnalytics/data/db` | 138.68 MB | 3 | Expected local-first data payload |
| `dist/CVMAnalytics/_internal` | 67.29 MB | 2924 | PyInstaller/runtime payload |
| `dist/CVMAnalytics/CVMAnalytics.exe` | 19.52 MB | 1 | Not the main weight source |
| `apps/web/.next/static` | 2.48 MB | 81 | Browser static assets |
| `apps/web/.next/standalone` | 21.45 MB | 1537 | Next standalone server |
| `apps/web/public` | 12.78 MB | 6 | Almost entirely one MP4 |
| `apps/web/node_modules` | 589.28 MB | 58760 | Developer-only install weight |
| `data/db/cvm_financials.db` | 121.49 MB | 1 | Source local SQLite DB |

Largest packaged files are processed/raw CVM CSVs and the SQLite DB. The largest observed CSV was `dist/CVMAnalytics/data/input/processed/itr_cia_aberta_DMPL_con_2020.csv` at about 127.92 MB.

### Database Snapshot

| Table | Source DB Rows | Packaged DB Rows |
|---|---:|---:|
| `companies` | 671 | not separately counted in packaged snapshot |
| `financial_reports` | 512213 | 523957 |
| `qa_logs` | 2326 | 2400 |
| `company_refresh_status` | 203 | not separately counted in packaged snapshot |
| `refresh_jobs` | 1 | not separately counted in packaged snapshot |

Both source and packaged DBs have 14 indexes, including indexes over company, account, statement, year, and period fields. Source DB freelist was zero pages.

### Route Bundle Diagnostics

| Route | First-load JS | Baseline/Max | Status |
|---|---:|---:|---|
| `/design-system` | 1,010,238 B | no budget | Large internal/demo route |
| `/demo-analysis` | 948,023 B | no budget | Large internal/demo route |
| `/empresas/[cd_cvm]` | 905,438 B | max 806,500 B | Fails budget |
| `/empresas` | 848,767 B | max 849,047 B | Passes narrowly |
| `/atualizar-base` | 738,235 B | no budget | Admin route |
| `/setores/[slug]` | 735,154 B | max 738,276 B | Passes narrowly |
| `/setores/[slug]/[sub_slug]` | 735,154 B | no budget | Same as sector detail |
| `/portfolio` | 693,936 B | no budget | Demo/portfolio route |
| `/` | 692,318 B | max 716,663 B | Passes |
| `/setores` | 689,558 B | max 850,000 B | Passes |

Largest static chunks observed after build:

| Chunk | Size |
|---|---:|
| `07o~osqztxvwt.js` | 222.2 KB |
| `0fgr_v4e.q9lu.css` | 173.1 KB |
| `0t0yn9s358aan.js` | 156.1 KB |
| `0ajk-anxzv8va.js` | 133.4 KB |
| `0-_11-t4t-h-6.js` | 130.8 KB |
| `03~yq9q893hmn.js` | 110.0 KB |
| `00sni6ba6it8r.js` | 99.7 KB |

### Read-Path Benchmark

`python scripts/benchmark_read_paths.py --runs 10` passed.

| Read path | Median | p95 | Notes |
|---|---:|---:|---|
| Companies directory, empty | 7.5 ms | 8.3 ms | Healthy synthetic benchmark |
| Companies directory, search | 2.9 ms | 4.5 ms | Healthy synthetic benchmark |
| Company years map, 20 companies | 2.7 ms | 3.5 ms | Healthy in benchmark |
| Available years | 0.4 ms | 0.8 ms | Healthy |
| Sector years map, all sectors | 32.3 ms | 45.2 ms | Uses scan plus temp distinct |
| Available company sectors | 22.3 ms | 26.0 ms | Moderate |
| Sector metric rows, all sectors | 42.5 ms | 68.6 ms | Uses temp group-by |
| Sector metric rows, single sector | 11.4 ms | 12.4 ms | Healthy |
| Company suggestions | 0.9 ms | 1.1 ms | Healthy |
| Sector companies | 0.6 ms | 1.0 ms | Healthy |

The e2e/dev run showed slower real-server paths than the synthetic benchmark:

| Runtime log signal | Observed latency |
|---|---:|
| `get_company_years_map` | up to about 4305 ms |
| `get_companies_by_cvm_ids` | up to about 790 ms |
| `get_sector_metric_rows` | about 267 ms |

This gap means query performance should be measured against the actual local DB and app flow before optimizing based only on synthetic benchmarks.

## 3. Findings and Priority

Scoring uses the investigation formula:

`Priority = User impact + Performance impact + Complexity reduction + Confidence - Risk - Effort - Aesthetic cost`

Scores are directional and should be recalculated after fixes or deeper profiling.

| Finding | Bucket | Priority | Evidence | Direction |
|---|---|---:|---|---|
| Packaged `data/input` is 3.65 GB | Quick win candidate after verification | 10 | Size inventory; build script does not explicitly copy `data/input` | Verify runtime/build dependency, then exclude or clean from package |
| Company detail API contract is broken | Immediate blocker | 9 | API/e2e failures; browser shows unavailable detail | Fix before serious company-detail performance profiling |
| `/empresas/[cd_cvm]` exceeds JS budget | Medium refactor | 7 | 905 KB vs 806 KB max | Chunk map, route-local lazy loading, shared shell review |
| Real app logs show slow company-year/company lookup paths | Medium refactor | 7 | e2e logs up to 4.3 s | Query plan on actual DB, cache strategy review |
| Home animation/readability depends on theme | Preserve but tune | 5 | Screenshot showed low contrast in light theme | Preserve rich animation, fix contrast/theme behavior later |
| Lint flags synchronous state updates in effects | Quick win candidate | 5 | `npm run lint` failures | Fix render hygiene after contract blocker |
| Internal/demo routes are large and visible | Approved scope cleanup | 4 | `/demo-analysis`, `/portfolio`; nav/footer links | Delete these routes in a future implementation pass; keep `/design-system` |
| Sectors hub is visually dense | Product/UX decision | 3 | 110 links, 261 rounded elements in sampled DOM | Consider progressive disclosure without flattening visual quality |
| `update-base-page.tsx` is 2000+ lines | Medium refactor | 3 | LOC hotspot, many controls/states | Split by workflow after runtime blockers |
| Node unit tests reparse modules due package type | DX cleanup | 1 | Unit-test warning only | Low priority unless test latency grows |

## 4. Bundle and Dependency Audit

### Major Dependencies to Keep as Core Unless Evidence Changes

| Dependency | Current role | Audit stance |
|---|---|---|
| `next`, `react`, `react-dom` | App runtime | Core |
| `@base-ui/react`, Radix primitives | UI primitives | Core, but watch overlap |
| `tailwindcss`, `shadcn/tailwind.css`, `tw-animate-css` | Styling and animation utilities | Keep, inspect CSS/chunk cost |
| `lucide-react` | Main icon set across app | Keep |
| `next-themes` | Theme switching | Keep, but theme default needs product decision |

### Dependencies Requiring Route/Usage Review

| Dependency | Evidence | Risk |
|---|---|---|
| `@remotion/player`, `remotion` | Imported by `apps/web/components/home/analysis-remotion-player.tsx`; home route uses dynamic client loading | Valuable polish, but can add JS/audio/render cost |
| `motion` | Used by interactive/demo components and likely design-system examples | Potentially justified for high-value animation; audit route leakage |
| `@hugeicons/*` | Used in `apps/web/components/feature-carousel.tsx` | Appears demo/design-system related; classify before changing |
| `react-countup` | Used in `apps/web/components/area-chart-medium.tsx` | Appears design-system/demo related |
| `react-day-picker`, `date-fns` | Calendar/date picker usage in analysis/demo components | Keep if date UX is real product scope; split if demo-only |

`npm ls --depth=0` passed but reported extraneous packages related to wasm/native runtime helpers. These should be reviewed only after package ownership is understood.

## 5. UI/UX Weight Review

### Visually Rich and Justified

| Area | Why it is justified |
|---|---|
| Company directory | Dense but navigable. Filters, cards/list controls, and status metadata support the analyst discovery loop. |
| Update base | Operational complexity is expected. The screen exposes status, scope, and progress clearly enough for an admin workflow. |
| Dark audit-desk direction | Strong product identity for financial analysis. The goal should be controlled contrast and hierarchy, not simplification into a plain dashboard. |
| Tables/cards in company analysis | Core product value is comparison and auditability; dense information is acceptable when hierarchy remains clear. |

### Visually Costly or Noisy Until Proven Valuable

| Area | Evidence | Concern |
|---|---|---|
| Home Remotion feature panel | Low contrast in light-theme sample; AudioContext browser warning | Preserve animation intent, but tune theme/readability |
| Sectors hub | 110 links, 261 rounded elements, long card grid | Scanning cost may be high for users trying to compare sectors |
| Header navigation | Visible internal/demo links plus several "Em breve" items | Can signal ambition, but also adds cognitive load |
| Global surface treatments | Many blur/shadow/gradient classes in shared recipes and page shell | Likely fine if restrained; inspect paint cost before reducing |
| Fluid `text-[clamp(...)]` headings | Used in home, companies, company header, portfolio | May create responsive polish, but can make density inconsistent |

## 6. Architecture and Maintainability Hotspots

| Area | Signal | Risk |
|---|---:|---|
| `src/read_service.py` | about 3660+ lines | Central source of truth, but very broad responsibility |
| `apps/web/components/update-base/update-base-page.tsx` | 2009 lines | Many state/effect paths in one client component |
| `apps/web/lib/api.ts` | 1571 lines | Large bridge/fallback contract surface |
| `desktop/services.py` | 1598 lines | Desktop service boundary is broad |
| `apps/web/lib/company-refresh-state.ts` | 1180 lines | State machine/business logic hotspot |
| `apps/web/app/design-system/page.tsx` | 769 lines | Internal route contributes bundle/scope weight |
| `apps/web/app/demo-analysis/page.tsx` | 787 lines | Demo route contributes bundle/scope weight |
| `apps/web/app/portfolio/page.tsx` | 659 lines | Shippable vs demo scope unclear |

Component areas by size:

| Area | Files | Lines |
|---|---:|---:|
| `apps/web/components/company` | 24 | about 3136 |
| `apps/web/components/update-base` | 6 | about 2276 |
| `apps/web/components/ui` | 23 | about 1477 |
| `apps/web/components/sectors` | 10 | about 1087 |
| `apps/web/components/companies` | 7 | about 1044 |
| `apps/web/components/shared` | 10 | about 1018 |
| `apps/web/components/home` | 6 | about 742 |

The codebase mostly uses local React state, effects, URL state, and custom hooks. No Redux/Zustand-style global store was found. That keeps dependency weight down, but complexity can still accumulate through repeated local state and duplicated loading/error flows.

## 7. Product Scope Review

| Surface | Product role | Current audit stance |
|---|---|---|
| `/` | Discovery and positioning | Core |
| `/empresas` | Company discovery | Core |
| `/empresas/[cd_cvm]` | Main analysis loop | Core, currently blocked by API contract failure |
| `/setores` | Sector discovery | Core/secondary, useful for context |
| `/setores/[slug]` | Sector analysis | Core/secondary, needs route slug verification |
| `/atualizar-base` | Local data maintenance | Core-accessible utility for every user |
| `/design-system` | Internal design catalog | Keep available |
| `/demo-analysis` | Demo/prototype | Delete in a future implementation pass |
| `/portfolio` | Portfolio/marketing-like page | Delete in a future implementation pass |
| Coming-soon nav items | Future scope | Potential cognitive load until enabled |

The product is at risk of shipping internal/editorial surfaces alongside the core analyst workflow. That does not mean they must be deleted. It means they should be classified as product, internal, demo, or hidden before optimization work starts.

## 8. Recommended Backlog

### Fix Before Performance Optimization

1. Align `CompanyInfoDTO`, `CompanyInfoPayload`, presenters, and tests around `sector_name` and `sector_slug`.
2. Re-run API and e2e tests after that fix.
3. Re-profile `/empresas/[cd_cvm]` only after the route renders real company detail content again.

### Quick Wins to Validate

1. Verify whether `dist/CVMAnalytics/data/input/raw` and `dist/CVMAnalytics/data/input/processed` are required at runtime.
2. If not required, adjust packaging/cleanup later only if distribution size becomes a problem. Current multi-GB folder size is acceptable for now.
3. Fix linted render-hygiene issues after the contract blocker:
   - `apps/web/components/company/company-freshness-card.tsx`
   - `apps/web/components/shared/use-combobox-navigation.ts`
   - `apps/web/components/update-base/use-sectors-catalog.ts`
   - `apps/web/components/sectors/sector-detail-desktop-loader.tsx`
4. Preserve Windows system-theme behavior, but fix light-theme contrast where visual treatments depend on a dark surface.

### Medium Refactors

1. Analyze route chunks for `/empresas/[cd_cvm]` and split route-local heavy pieces only where the route budget proves it.
2. Measure real local DB query plans for `get_company_years_map` and `get_companies_by_cvm_ids`.
3. Split `update-base-page.tsx` by workflow state and UI region after tests are green.
4. Review `apps/web/lib/api.ts` for repeated bridge/fallback patterns and contract duplication, but avoid changing the data boundary until the API contract is stable.

### Strategic Product Decisions

1. Remove `/demo-analysis` and `/portfolio` in a future implementation pass, including their navigation/footer references and route-local dependencies where safe.
2. Keep `/design-system` visible in navigation/footer.
3. Keep "Em breve" navigation items visible before the features exist.
4. Keep `/atualizar-base` accessible to every user, but continue auditing its complexity because it is part of the main product surface.

### Preserve Unless Proven Costly

1. Dark audit-desk visual identity.
2. Dense financial cards/tables when they support comparison and auditability.
3. Teal/financial accents when they indicate action, focus, or analytical state.
4. Home animation concept, if contrast and startup cost are controlled.

### Avoid for Now

1. Do not remove dependencies based only on package names.
2. Do not replace Remotion/Motion before route/chunk evidence confirms they are user-visible bottlenecks.
3. Do not optimize SQLite indexes before the real slow queries are reproduced with `EXPLAIN QUERY PLAN`.
4. Do not flatten the UI purely to reduce visual effects. The target is professional polish with measured restraint.

## 9. Files and Areas to Inspect Next

| Area | Files/Folders |
|---|---|
| Desktop packaging | `desktop/build_desktop.ps1`, `desktop/app.spec`, `dist/CVMAnalytics/data` |
| Web bundle | `apps/web/.next/diagnostics/route-bundle-stats.json`, `apps/web/next.config.ts`, `apps/web/package.json` |
| App shell | `apps/web/app/layout.tsx`, `apps/web/app/globals.css`, `apps/web/components/shared/site-header.tsx`, `apps/web/components/shared/site-footer.tsx` |
| Company detail | `apps/web/app/empresas/[cd_cvm]/page.tsx`, `apps/web/components/company`, `apps/api/app/presenters.py`, `src/contracts.py`, `src/read_service.py` |
| Company directory | `apps/web/app/empresas/page.tsx`, `apps/web/components/companies` |
| Sectors | `apps/web/app/setores`, `apps/web/components/sectors`, `src/query_layer.py` |
| Update base | `apps/web/components/update-base/update-base-page.tsx`, `apps/web/lib/company-refresh-state.ts`, `desktop/bridge.py` |
| Internal/demo scope | `apps/web/app/design-system`, `apps/web/app/demo-analysis`, `apps/web/app/portfolio`, `apps/web/components/feature-carousel.tsx`, `apps/web/components/area-chart-medium.tsx` |
| Public assets | `apps/web/public/ambient/abstract-loop-background.mp4` |

## 10. Validation Appendix

| Command | Result | Notes |
|---|---|---|
| `npm run build` in `apps/web` | Passed | Next build completed and regenerated route diagnostics |
| `python scripts/perf_guardrail.py check --baseline docs/perf/performance_baseline.json` | Failed | API snapshot fails because `CompanyInfoPayload` requires `sector_name` and `sector_slug`; temp DB cleanup then hit a Windows permission error |
| `python scripts/benchmark_read_paths.py --runs 10` | Passed | Synthetic read paths mostly fast; sector aggregate paths moderate |
| `npm run lint` in `apps/web` | Failed | React hook lint failures and one missing dependency warning |
| `npm run typecheck` in `apps/web` | Passed | TypeScript check passed |
| `npm run test:unit` in `apps/web` | Passed | 122 tests passed; Node emitted module type reparsing warnings |
| `pytest tests/ -q` | Passed | 158 tests passed |
| `pytest apps/api/tests -q` | Failed | 9 failed, 112 passed; failures center on company info contract/presenter mismatch |
| `npm run test:e2e` in `apps/web` | Failed | 5 failed, 5 passed; company detail unavailable and sector strict locator issue |

Browser screenshots captured during the audit:

- `output/playwright/app-weight-audit/home-desktop.png`
- `output/playwright/app-weight-audit/companies-desktop.png`
- `output/playwright/app-weight-audit/company-detail-desktop.png`
- `output/playwright/app-weight-audit/sectors-desktop.png`
- `output/playwright/app-weight-audit/sector-detail-desktop.png`
- `output/playwright/app-weight-audit/update-base-desktop.png`
- `output/playwright/app-weight-audit/home-mobile.png`
- `output/playwright/app-weight-audit/companies-mobile.png`

## 11. Questions That Affect the Next Phase

All initial questions have been answered. No remaining product-scope questions are blocking the next implementation phase.
