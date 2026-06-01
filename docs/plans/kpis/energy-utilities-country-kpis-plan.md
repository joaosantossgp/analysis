# Energy Utilities — Country-Level KPI Layer (v1 Plan)

**Status:** Planning only. No implementation in this document.
**Owner:** João (jaotrab@gmail.com)
**Author:** AI agent (planning + refinement pass)
**Last updated:** 2026-06-01
**Canonical location:** `docs/plans/kpis/energy-utilities-country-kpis-plan.md`

> Canonical planning record for the Energy Utilities country-level KPI initiative
> **and** the broader Sector KPI Registry it seeds. Multiple AI agents continue
> from this file. Do **not** start coding until the Implementation Readiness
> Checklist (§18) is green and João approves. Keep this doc the single source of
> truth — do not fork into scratch notes.

---

## 0. How to use this document (for the next agent)

- Read `AGENTS.md` and `docs/CONTEXT.md` before touching `src/` or `apps/api/`.
- Active frontend = `apps/desktop-web` (Vite SPA). Active runtime = pywebview
  bridge (`apps/desktop-web/src/lib/bridge/adapter.ts` → `window.pywebview.api`
  → `desktop/bridge.py` → `src/`). **The desktop app does not use the HTTP API.**
  Shared logic lives in `src/` so both the desktop bridge and `apps/api` reuse it.
- This KPI layer is **net-new and additive**. It does **not** modify the existing
  company financial KPI engine (`src/kpi_engine.py`), the CVM/B3 pipeline, or
  sector classification. It is the **first sector-specific implementation of a
  centralized Sector KPI Registry** (§17), not a one-off table.

---

## 1. Executive summary

CVMAnalytics computes **company-level** financial KPIs from CVM filings
(`src/kpi_engine.py`) and groups companies into sectors
(`src/sector_taxonomy.py`, GICS). It has **no country/macro KPI layer** and **no
central KPI catalog** — KPI definitions live inline in the engine and are consumed
directly by readers/exporters.

This plan delivers (a) a **v1 country-level Energy Utilities KPI catalog** and
(b) the **architecture for a centralized Sector KPI Registry** that Energy
Utilities is the first tenant of. The KPI layer gives sector/macro context to
Brazilian energy-utility equities: country electricity matrix, hydro/thermal
exposure, renewable trajectory, demand growth, carbon intensity, import
dependence.

**Source strategy (verified this pass — see §6):**
1. **OWID Energy Dataset = primary** (`source_priority = 1`). One annual
   country×year CSV + published codebook. Verified to carry nearly every v1 KPI.
   **Key fact:** OWID's *electricity* columns are themselves sourced from **Ember
   Yearly Electricity Data** + Energy Institute. So OWID-first already delivers
   Ember's annual electricity matrix, pre-cleaned and ISO-keyed.
2. **Ember API = fallback / complement** (`source_priority = 2`). Verified to
   exist (free email-gated API key, Swagger at `api.ember-energy.org/docs`,
   yearly + monthly, capacity dataset). Direct Ember adds value over OWID **only**
   for: **installed capacity** (OWID lacks it), **monthly** granularity, and
   **freshness** between OWID refreshes. Exact Ember field names are **not yet
   verified** (key-gated) → capacity is `blocked_by_source_verification`.

**v1 posture:** annual only; OWID-only ingestion; Ember integrated **after**
field-level verification; capacity deferred; ~18 curated KPIs. Small, auditable,
offline-first.

**Architecture fit:** reuse SQLite/SQLAlchemy (`src/database.py`, WAL),
`AppPaths` roots (`src/settings.py`), snapshot+stale+refresh-log conventions
(`src/refresh_service.py`, `src/refresh_jobs.py`), DTO read layer
(`src/read_service.py`), xlsxwriter exporter with WSP formats
(`src/excel_exporter.py`). Additive; no changes to existing tables or
`kpi_engine.py`.

---

## 2. Repo discovery notes (inspected this pass)

| Area | Finding | Path |
|---|---|---|
| Agent contract | English-only target; inspect-before-edit; data work = auditability first; do not touch removed `apps/web` Next.js | `AGENTS.md` |
| Active frontend | Vite SPA confirmed; flat route `.tsx` files | `apps/desktop-web/src/routes/*.tsx` |
| Frontend libs | `lib/api/`, `lib/bridge/adapter.ts`, `lib/indicators/`, `lib/format/`; `components/{indicators,data,export,surface,shell,ui}` | `apps/desktop-web/src/` |
| Runtime bridge | pywebview; `def method(self, params=None)` → dict; lazily builds `CVMReadService` | `desktop/bridge.py` |
| Read layer | `CVMReadService` → typed DTOs (`SectorDirectoryDTO`, `SectorDetailDTO`, `KPIBundle`, …); `list_sectors`, `get_sector_detail`, `get_kpi_bundle` | `src/read_service.py` (4939 lines) |
| **Company KPI engine** | Catalog = **module-level Python list of tuples** `_KPI_CATALOG` → DataFrame; per-KPI `FORMAT_TYPE`, `HIGHER_IS_BETTER`, `UNIDADE`; pct/ratio formatting; sets `_PCTS`, `_HIGHER_IS_BETTER`. **Company-level CVM accounts only. No source/geography/registry concept.** | `src/kpi_engine.py:21` |
| Sector taxonomy | Canonical name + slugify + GICS bucket SQL; no country/geography | `src/sector_taxonomy.py` |
| DB | SQLite/SQLAlchemy; `init_db_tables` + `ensure_*_tables_for_connection(conn)`; `CREATE TABLE IF NOT EXISTS`; WAL, `synchronous=OFF`; default `data/db/cvm_financials.db` | `src/database.py:20`, `src/db.py` |
| Data layout | Buckets: `.zip`→raw, `.csv`→processed; `infer_canonical_bucket`; legacy-path sync planner | `src/data_layout.py` |
| Data paths | `AppPaths`: `raw_dir`, `processed_dir`, `metadata_dir`, `cache_dir`, `db_dir`; env-overridable; packaged root `%USERPROFILE%\Documents\CVMAnalytics` | `src/settings.py` |
| Refresh model | `HeadlessRefreshService`; refresh runtime tables; **snapshot + stale-fallback + refresh-log already implemented** for market-cap | `src/refresh_service.py`, `src/refresh_jobs.py` |
| Excel exporter | xlsxwriter; **negatives in parentheses, zero → `-`** (`'0.00"x";(0.00"x");-'`); hidden `raw_*` audit sheets | `src/excel_exporter.py:869` |
| HTTP API mirror | FastAPI `apps/api` — **not** used by desktop; shared logic must live in `src/` | `apps/api/app/` |
| Docs convention | Flat `docs/*.md` + `reference/`, `decisions/` (ADRs), `governance/`, `skills/`. `docs/plans/` created by this initiative. | `docs/` |
| Tests | `pytest tests/` (core/desktop), `pytest apps/api/tests/` (hosted API); fixtures-based | `tests/`, `apps/api/tests/`, `pytest.ini` |

**No conflicts / legacy risk for this task.** Additive new modules only; no
inactive code touched.

---

## 3. Proposed canonical `.md` location

`docs/plans/kpis/energy-utilities-country-kpis-plan.md` (this file).
`docs/` is the doc root; `reference/` and `decisions/` are reserved (active
reference + ADRs); no `docs/plans/` existed. `docs/plans/<initiative>/` is
additive and matches the flat-Markdown convention. Once the data model + registry
are ratified, add a one-line ADR stub under `docs/decisions/` pointing here.

---

## 4. KPI taxonomy (classification model)

Logical union of fields each KPI carries. Split across registry tables in §7/§17.
snake_case, English-only (new module → adopt `AGENTS.md` English target; the
existing company engine's Portuguese UPPER columns are not changed).

| Field | Type | Notes |
|---|---|---|
| `kpi_id` | TEXT PK | Namespaced slug, e.g. `energy_utilities.country.elec_renewables_share`. |
| `display_name` | TEXT | English. |
| `description` | TEXT | One-line analyst definition. |
| `kpi_type` | enum | `mix_share` \| `intensity` \| `per_capita` \| `volume` \| `emissions` \| `trade` \| `transition` \| `capacity` \| `growth`. |
| `sector` | TEXT | `Energy Utilities` (v1). |
| `subsector` | TEXT null | e.g. `Power Generation`, `Electricity Market`. |
| `macro_category` | enum | `electricity_mix` \| `energy_mix` \| `renewables` \| `fossil_dependence` \| `hydro` \| `thermal` \| `nuclear` \| `demand` \| `generation` \| `capacity` \| `emissions` \| `carbon_intensity` \| `transition` \| `trade` \| `intensity`. |
| `geography_type` | enum | `country` (v1) \| `region` \| `world`. |
| `country` / `iso_code` | TEXT | Display name / ISO-3166 alpha-3 (OWID `iso_code`) — canonical join key. |
| `period` / `frequency` | INT / enum | Year / `annual` (v1) \| `monthly` (deferred). |
| `unit` | TEXT | `%`, `TWh`, `GW`, `kWh/capita`, `gCO2/kWh`, `MtCO2e`, `kWh/$`. |
| `source` / `source_priority` | enum / INT | `OWID`(1) \| `EMBER`(2). |
| `source_field` | TEXT | Original column/field preserved verbatim. |
| `calculation_method` | TEXT | `direct` \| `derived_yoy` \| `derived_trend` \| formula. |
| `data_quality_status` | enum | `ok` \| `partial` \| `missing` \| `fallback_used` \| `conflict` \| `stale`. |
| `last_updated` | ISO | Snapshot/refresh timestamp. |
| `audit_notes` / `source_caveats` | TEXT | Definition deltas, substitution-method notes. |
| `dashboard_use_case` / `financial_modeling_use_case` | TEXT | Where used / how analysts use it. |

Full registry field model (superset, for centralization) is in §17.3.

---

## 5. v1 Energy Utilities KPI catalog (execution-ready)

Curated, **not exhaustive**. OWID field names **verified** against the OWID
energy codebook (§6.1). Ember field names **not verified** (key-gated) → any
KPI depending on Ember-only data is `blocked_by_source_verification`.

`calc`: `direct` = passthrough; `derived_yoy` / `derived_trend` = computed
locally on ingest. `primary_source` = OWID unless noted. `fallback` = EMBER where
a direct-Ember equivalent exists (note: for electricity KPIs OWID is *already*
Ember-derived, so Ember-direct fallback only helps freshness/monthly).

### 5.1 Catalog table

| kpi_id (`…country.` prefix) | display_name | category | kpi_type | macro_category | geo | freq | unit | primary_source | primary_source_field | fallback_source | fallback_source_field | calc | v1_status | dashboard_priority | excel_export_priority | audit_notes | source_caveats |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `elec_renewables_share` | Renewable Share of Electricity | electricity_matrix | mix_share | renewables | country | annual | % | OWID | `renewables_share_elec` | EMBER | ⚠ tbd | direct | **v1_required** | lead | required | Substitution method affects absolute TWh, not share | OWID elec = Ember-sourced |
| `elec_fossil_share` | Fossil Share of Electricity | electricity_matrix | mix_share | fossil_dependence | country | annual | % | OWID | `fossil_share_elec` | EMBER | ⚠ tbd | direct | **v1_required** | lead | required | coal+oil+gas | — |
| `elec_hydro_share` | Hydro Share of Electricity | electricity_matrix | mix_share | hydro | country | annual | % | OWID | `hydro_share_elec` | EMBER | ⚠ tbd | direct | **v1_required** | lead | required | Key for BR hydrology risk | — |
| `elec_low_carbon_share` | Low-Carbon Share of Electricity | electricity_matrix | mix_share | renewables | country | annual | % | OWID | `low_carbon_share_elec` | EMBER | ⚠ tbd | direct | v1_optional | secondary | required | renewables+nuclear | — |
| `elec_gas_share` | Gas Share of Electricity | electricity_matrix | mix_share | thermal | country | annual | % | OWID | `gas_share_elec` | EMBER | ⚠ tbd | direct | **v1_required** | secondary | required | Thermal dispatch proxy | — |
| `elec_coal_share` | Coal Share of Electricity | electricity_matrix | mix_share | thermal | country | annual | % | OWID | `coal_share_elec` | EMBER | ⚠ tbd | direct | v1_optional | secondary | optional | — | — |
| `elec_solar_share` | Solar Share of Electricity | electricity_matrix | mix_share | renewables | country | annual | % | OWID | `solar_share_elec` | EMBER | ⚠ tbd | direct | v1_optional | detail_only | optional | — | — |
| `elec_wind_share` | Wind Share of Electricity | electricity_matrix | mix_share | renewables | country | annual | % | OWID | `wind_share_elec` | EMBER | ⚠ tbd | direct | v1_optional | detail_only | optional | — | — |
| `elec_nuclear_share` | Nuclear Share of Electricity | electricity_matrix | mix_share | nuclear | country | annual | % | OWID | `nuclear_share_elec` | EMBER | ⚠ tbd | direct | v1_optional | detail_only | optional | Low for BR | — |
| `elec_generation_total` | Total Electricity Generation | demand_generation | volume | generation | country | annual | TWh | OWID | `electricity_generation` | EMBER | ⚠ tbd | direct | **v1_required** | lead | required | — | — |
| `elec_demand_total` | Total Electricity Demand | demand_generation | volume | demand | country | annual | TWh | OWID | `electricity_demand` | EMBER | ⚠ tbd | direct | **v1_required** | lead | required | demand=gen+net imports−losses | def. differs slightly vs Ember |
| `elec_demand_per_capita` | Electricity Demand per Capita | demand_generation | per_capita | demand | country | annual | kWh | OWID | `electricity_demand_per_capita` | EMBER | ⚠ tbd | direct | v1_optional | secondary | optional | population-dependent | — |
| `elec_demand_growth_yoy` | Electricity Demand Growth (YoY) | demand_generation | growth | demand | country | annual | % | OWID | `electricity_demand` | EMBER | ⚠ tbd | derived_yoy | **v1_required** | secondary | required | derived locally | revisions shift YoY |
| `elec_carbon_intensity` | Carbon Intensity of Electricity | emissions | intensity | carbon_intensity | country | annual | gCO₂/kWh | OWID | `carbon_intensity_elec` | EMBER | ⚠ tbd | direct | **v1_required** | lead | required | lifecycle basis (Ember) | scope vs Ember-direct may differ |
| `elec_ghg_emissions` | Power-Sector GHG Emissions | emissions | emissions | emissions | country | annual | MtCO₂e | OWID | `greenhouse_gas_emissions` | EMBER | ⚠ tbd | direct | v1_optional | secondary | optional | lifecycle | — |
| `elec_net_imports_share` | Net Imports as % of Demand | trade | trade | trade | country | annual | % | OWID | `net_elec_imports_share_demand` | EMBER | ⚠ tbd | direct | **v1_required** | secondary | required | structural import dependence | — |
| `elec_net_imports` | Net Electricity Imports | trade | trade | trade | country | annual | TWh | OWID | `net_elec_imports` | EMBER | ⚠ tbd | direct | v1_optional | detail_only | optional | **can be negative** (export) | parentheses in Excel |
| `energy_renewables_share` | Renewable Share of Primary Energy | energy_matrix | mix_share | renewables | country | annual | % | OWID | `renewables_share_energy` | — | — | direct | v1_optional | secondary | optional | Energy Institute origin | broader than electricity |
| `energy_fossil_share` | Fossil Share of Primary Energy | energy_matrix | mix_share | fossil_dependence | country | annual | % | OWID | `fossil_share_energy` | — | — | direct | v1_optional | secondary | optional | Energy Institute origin | — |
| `elec_renewables_share_5y_chg` | Renewable Share Δ (5y) | transition | transition | transition | country | annual | pp | OWID | `renewables_share_elec` | — | — | derived_trend | v1_optional | secondary | optional | derived; transition signal | needs ≥5y coverage |
| `capacity_installed_total` | Total Installed Capacity | capacity | capacity | capacity | country | annual | GW | EMBER | ⚠ `capacity_annual` (field tbd) | — | — | direct | **blocked_by_source_verification** | not_in_v1_dashboard | optional | OWID has no capacity; Ember dataset exists, field unverified | needs Ember API key + Swagger field check |

### 5.2 Counts
- **Total v1 catalog rows:** 21.
- **`v1_required`: 9** — `elec_renewables_share`, `elec_fossil_share`,
  `elec_hydro_share`, `elec_gas_share`, `elec_generation_total`,
  `elec_demand_total`, `elec_demand_growth_yoy`, `elec_carbon_intensity`,
  `elec_net_imports_share`.
- **`v1_optional`:** 11.
- **`blocked_by_source_verification`:** 1 (`capacity_installed_total`).
- **`fallback_only` / `defer`:** 0 hard-defer in v1; monthly + capacity deferred
  via blocked/decision (§16).

> The 9 `v1_required` KPIs answer the core analyst questions: hydro-heavy?
> (`elec_hydro_share`), thermal/fossil dispatch exposure? (`elec_fossil_share`,
> `elec_gas_share`), getting more renewable? (`elec_renewables_share` +
> 5y trend), demand growing? (`elec_demand_total`, `elec_demand_growth_yoy`),
> carbon improving? (`elec_carbon_intensity`), structural importer?
> (`elec_net_imports_share`), system scale (`elec_generation_total`).

---

## 6. Source verification log (this pass)

### 6.1 OWID — verified (codebook `owid-energy-codebook.csv`)

CSV: `https://owid-public.owid.io/data/energy/owid-energy-data.csv` ·
Codebook: `owid-energy-codebook.csv` · Cadence: **annual** (file refreshed
several times/year) · License **CC-BY** · Join key `iso_code` (alpha-3) + `year`.

| Field | Meaning | Unit | Freq | Coverage | v1-suitable | Caveat |
|---|---|---|---|---|---|---|
| `electricity_generation` | Total electricity generated | TWh | annual | ~200 geos | yes | source: Ember Yearly Electricity |
| `electricity_demand` | Electricity demand | TWh | annual | broad | yes | gen+net imports−losses |
| `electricity_demand_per_capita` | Demand per person | kWh | annual | broad | yes | population-dependent |
| `renewables_share_elec` | Renewable % of electricity | % | annual | broad | yes | substitution method (shares OK) |
| `fossil_share_elec` | Fossil % of electricity | % | annual | broad | yes | coal+oil+gas |
| `low_carbon_share_elec` | Low-carbon % | % | annual | broad | yes | renewables+nuclear |
| `hydro/solar/wind/nuclear/coal/gas_share_elec` | Per-source % | % | annual | broad | yes | granular detail |
| `renewables_share_energy` / `fossil_share_energy` | Primary-energy shares | % | annual | broad | optional | Energy Institute origin |
| `primary_energy_consumption` | Primary energy | TWh | annual | broad | optional | EIA/Energy Institute |
| `energy_per_capita` | Primary energy per capita | kWh/person | annual | broad | optional | — |
| `carbon_intensity_elec` | GHG per unit electricity | gCO₂/kWh | annual | broad | yes | Ember; lifecycle |
| `greenhouse_gas_emissions` | Lifecycle power emissions | MtCO₂e | annual | broad | optional | Ember |
| `net_elec_imports` | Imports − exports | TWh | annual | broad | optional | can be negative |
| `net_elec_imports_share_demand` | Net imports % of demand | % | annual | broad | yes | structural dependence |

Original providers per codebook: **Ember** (electricity, intensity, emissions,
trade), **Energy Institute Statistical Review** (energy shares), **U.S. EIA**
(primary energy), population sources. Source dates span 2019–2026; historical
series typically reach back to mid-20th century for energy, ~1985+/2000+ for
electricity depending on geography (confirm exact start per country in Phase 2).

### 6.2 Ember — partially verified (API exists; field names NOT verified)

| Question | Finding |
|---|---|
| API docs accessible? | Yes at `api.ember-energy.org/docs` (Swagger). **JS-rendered** — not statically scrapable; root site 403s WebFetch (bot block). |
| Static or JS-rendered? | **JS-rendered** Swagger UI. |
| API key / auth? | **Yes** — free API key, email-verified, requested from Ember's data/API page. |
| Datasets | Yearly Electricity (generation, capacity, emissions, demand) >200 geos; Monthly electricity (generation, emissions, demand) 88 geos; Monthly wind/solar capacity 25 countries. |
| Field names | **Not verified.** GitHub `ember-energy/ember-data-api` README implies tables `generation_annual`, `capacity_annual`, `intensity_annual` — table-level only, **not** column/field names. |
| Units | Not field-verified (expected TWh, GW, gCO₂/kWh, MtCO₂e). |
| Frequency | **Annual + monthly** both available. |
| Geography | Yearly >200; monthly 88. |
| Installed capacity? | **Dataset exists** (`capacity_annual` / monthly wind+solar). Exact fields unverified → KPI `blocked_by_source_verification`. |
| Power-sector emissions / carbon intensity? | Yes (`intensity_annual`, emissions in yearly/monthly). |
| Annual data? | Yes. Monthly? Yes (deferred in v1). |

**Conclusion:** Ember is real and richer than OWID for capacity/monthly, but
because OWID's electricity matrix is *already Ember-derived annually*, **v1 needs
no direct Ember dependency**. Direct Ember is required only for capacity (blocked
until a key + Swagger field check) and future monthly/freshness. All Ember
`source_field` cells remain ⚠ `source_verification_required`.

### 6.3 Conflict & lineage rules (unchanged intent, sharpened)
- Canonical displayed value follows priority (OWID). Non-selected source value is
  preserved in the raw snapshot and may be stored in a shadow column
  (`value_owid` / `value_ember`); never discarded.
- If both exist and `abs(owid−ember)/max(|owid|,ε) > threshold` (default 10% for
  shares; configurable per `kpi_type`) → `data_quality_status='conflict'` +
  `source_conflict` flag; surfaced in tooltip + Excel DQ tab. **Never silently
  merged.**
- Definition deltas to record in `audit_notes`: renewables substitution method
  (OWID), demand vs consumption, emissions lifecycle vs direct scope, country/ISO
  naming.

---

## 7. Local-first storage / data model

- **Reuse SQLite.** Recommend a **separate file `data/db/energy_kpis.db`** (the
  registry DB), created via the existing `ensure_*_tables_for_connection(conn)`
  pattern + WAL — full decoupling from `cvm_financials.db`, independent refresh,
  zero migration risk, easy to ship or skip. (Decision §16.6.)
- **Raw snapshots immutable** — new fetch = new `snapshot_id`; never overwrite.
- **Offline-first** — all reads hit local SQLite/files; **no network on read**.
  Fetch only on explicit user refresh or first-run seed.
- **Data roots** (extend `AppPaths`, env-overridable): raw →
  `data/raw/energy/owid/<snapshot_id>/…` (+ codebook copy) and
  `…/ember/<snapshot_id>/…`; normalized → `data/db/energy_kpis.db`; metadata →
  `data/metadata/energy/` (manifest, checksums). Packaged users under
  `%USERPROFILE%\Documents\CVMAnalytics`.

### 7.1 Tables (registry-aligned — see §17 for the unified model)

| Table | Purpose | Key columns |
|---|---|---|
| `kpi_catalog` | KPI definitions (§17.3 fields) | `kpi_id` PK, …, `owner_module`, `source_verification_status`, `availability_status` |
| `country_dimension` | Country master | `iso_code` PK, `country_name`, `region`, `is_v1_scope` |
| `country_kpi_values` | Tidy facts | (`kpi_id`,`iso_code`,`period`) PK, `value`, `unit`, `source`, `source_priority`, `source_field`, `data_quality_status`, `last_updated`, `snapshot_id`, `value_owid`, `value_ember`, `source_conflict` |
| `kpi_sources` | Source registry | `source` PK, `display_name`, `base_url`, `license`, `default_priority`, `cadence`, `retrieval_method`, `schema_version`, `notes` |
| `source_snapshots` | Immutable fetch ledger | `snapshot_id` PK, `source`, `fetched_at`, `file_path`, `sha256`, `row_count`, `source_version_label`, `status` |
| `kpi_refresh_log` | Run log | `run_id` PK, `started_at`, `finished_at`, `source`, `status`, `rows_ingested`, `rows_conflict`, `error`, `triggered_by` |
| `data_quality_checks` | Validation results | `check_id` PK, `run_id`, `check_name`, `severity`, `passed`, `details_json`, `created_at` |

Tidy `country_kpi_values` (one row per kpi×country×year) keeps queries + Excel
pivots cheap (low CPU/memory). Names are proposals; reuse a better existing
convention if one is found.

### 7.2 Freshness / failure / reproducibility
- `last_refresh` per source (`kpi_sources`) + per snapshot (`source_snapshots`).
- Stale: OWID > 90 days → mark stale, banner, still serve cache offline.
- Failed refresh: keep last good snapshot; log in `kpi_refresh_log`; non-blocking
  warning (mirror market-cap fallback in `src/refresh_service.py`).
- Cache invalidation keyed by `snapshot_id` + `source_version_label`.
- Every value row → resolvable `snapshot_id` = exact provenance.
- Low footprint: OWID CSV is a few MB; chunked read, filter to v1 countries +
  v1 columns before insert; ingest off the UI thread.

---

## 8. Ingestion / update plan

1. **Trigger:** user "Update energy data" or first-run seed. **Never** auto-fetch
   on app start (startup-perf hard requirement).
2. Fetch OWID CSV + codebook → immutable snapshot dir + checksum →
   `source_snapshots` row.
3. Normalize: select v1 columns, melt wide→tidy (country, iso, year, kpi_id,
   value), drop non-country aggregates unless `geography_type` allows, attach
   units from codebook.
4. Ember (**only after field verification**; v1 = capacity blocked): snapshot
   JSON, map to tidy shape, set `fallback_used` where it fills OWID gaps.
5. Merge by priority (§6.3), compute `derived_yoy`/`derived_trend`, set
   `data_quality_status`, upsert `country_kpi_values`.
6. Validations (§9) → `data_quality_checks` + `kpi_refresh_log`.
7. Atomic swap: stage → validate → commit; on failure keep prior data + log.

All in shared `src/energy_kpi/` (proposed), invoked by bridge + `apps/api`. No
network on read path.

---

## 9. Data quality & audit plan

Each check → a `data_quality_checks` row (`info|warn|error`):
schema (expected OWID columns + unit match); required fields (`iso_code`,
`period`, `value`); ISO validity (alpha-3 in `country_dimension`); unit
consistency vs `kpi_catalog.unit`; duplicate (`kpi_id`,`iso_code`,`period`);
missing-value coverage report; impossible negatives (shares/volumes/per-capita
≥0; `net_elec_imports` may be negative; intensity ≥0); share bounds [0,100];
YoY outliers (warn beyond threshold, e.g. share jump >30pp); coverage gaps;
fallback flags; conflict flags (top deltas listed); reproducibility (every value
→ resolvable `snapshot_id`). Conflicts/fallbacks always visible (tooltip + Excel
DQ tab), never silently resolved.

---

## 10. UI / dashboard plan (`apps/desktop-web`)

Follow `docs/skills/CVMANALYTICS_VITE_UI_SKILL.md` + existing design system
(Tailwind tokens, `@base-ui/react`, sector colors, OKLCH). English-only.
Additive to current routes. Surfaces: Energy Utilities sector page (or a
"Macro / Country" tab on the Energy sector detail) with country electricity
matrix + transition snapshot; country comparison; KPI category filter; KPI
detail drilldown with full source lineage; light company context panel (single
configured country, default Brazil — no company→country mapping yet); source/
audit tooltip (source badge, priority, "sources disagree" on conflict,
last-updated, caveats); loading/empty/error/**stale** states; filters by country,
year, category, source, unit; Excel export button reusing `components/export`.

**Dashboards must request KPI groups through the shared read service / catalog
query layer (§17.4) — no hardcoded KPI lists in the frontend.** Bridge methods
(style `params=None`→dict): `get_kpi_catalog`, `get_country_kpi_series`,
`get_country_kpi_compare`, `get_energy_kpi_health`, `refresh_energy_kpis`,
`export_country_kpis_excel`.

---

## 11. Excel export plan

Reuse `src/excel_exporter.py` conventions (already: negatives in parentheses,
zero → `-`, hidden `raw_*` audit sheets). Tabs: **KPI Catalog** (filtered by
`excel_export_priority`); **Country KPI Time Series** (country×year per KPI);
**Source Metadata** (source, base URL, license, cadence, snapshot id/date,
checksum, priority); **Data Quality Checks**. Rules: no merged cells; units in
headers ("Renewable Share (%)", "Generation (TWh)"); negatives in parentheses
(net imports); zeros `-`; per-KPI source caveats footnoted from `audit_notes`;
every value traceable to `snapshot_id`. Export set driven by
`excel_export_priority`, not a hardcoded list.

---

## 12. Implementation roadmap (phased; no code yet)

Each phase: goal · files/modules · risks · validation · acceptance.

- **Phase 0 — Discovery & ratify** (done this pass): confirm stack/paths/
  conventions; this doc. Accept: plan + §16 decisions approved.
- **Phase 1 — Taxonomy & catalog**: finalize §4/§5 + §17.3 registry fields; draft
  `kpi_catalog` seed (data). Accept: ≤~21 KPIs, each with verified OWID field +
  unit; Ember-only KPIs marked blocked.
- **Phase 2 — Source verification**: OWID done; **obtain Ember API key, read
  Swagger, confirm capacity/intensity field names + units + monthly shape**;
  resolve all ⚠. Accept: every ⚠ resolved or explicitly deferred.
- **Phase 3 — Local storage**: finalize §7 tables; separate `energy_kpis.db`;
  extend `AppPaths`. Files: `src/settings.py`, `src/energy_kpi/schema.py`
  (`ensure_energy_kpi_tables_for_connection`), `src/db.py` wiring. Accept:
  additive; idempotent create; offline read works.
- **Phase 4 — Ingestion**: snapshot→normalize→merge→upsert. Files:
  `src/energy_kpi/{ingest_owid,ingest_ember,merge,refresh}.py`. Accept:
  user-triggered refresh → tidy values + snapshots + log; immutable snapshots.
- **Phase 5 — DQ & audit**: §9 → `data_quality_checks`, conflict/fallback flags.
  File `src/energy_kpi/quality.py`. Accept: conflicts/fallbacks surfaced.
- **Phase 6 — UI**: §10 surfaces + read/catalog query methods + DTOs. Files:
  `src/read_service.py` or `src/energy_kpi/read.py`, `desktop/bridge.py`,
  `apps/desktop-web/src/{routes,lib/api,components}`. Validate: `npm --prefix
  apps/desktop-web run typecheck` + dev-server visual. Accept: KPIs visible,
  source-cited, filterable, no hardcoded KPI lists.
- **Phase 7 — Excel**: §11 four-tab workbook. File `src/energy_kpi/excel.py` or
  extend exporter. Accept: no merged cells, units, parentheses, zeros `-`,
  traceable.
- **Phase 8 — Tests**: `tests/energy_kpi/…` fixtures. Validate `pytest tests/` +
  typecheck + offline-read test. Accept: §16/§18 green.

---

## 13. Risks & caveats

Definition mismatch OWID↔Ember (substitution method, demand vs consumption,
emissions scope) → document + conflict-flag. Unit differences (TWh/GWh,
kWh/MWh, gCO₂/kWh vs tCO₂/MWh) → normalize on ingest, store source unit. Partial
country coverage → coverage report, `missing`, no fake fill. **Ember API key /
rate limits / field names unverified** → Phase 2 gate; capacity blocked. Refresh
cadence differences → per-source stale thresholds. Historical revisions →
snapshots make them visible/reproducible. Cache corruption → checksums, re-fetch
on mismatch, keep last good. Heavy downloads / startup degradation → no startup
fetch, chunked off-thread ingest, small filtered footprint. Mixed-source
confusion → source badges + canonical policy + "disagree" indicator. Stale data →
banner + last-updated; offline serves cache. Misleading cross-country comparisons
→ always show units + source. **Overfitting to Energy Utilities** → §17 registry
keeps schema sector-agnostic (`sector`/`macro_category`/`domain` are columns, not
hardcode).

---

## 14. Non-goals (v1)

Implementation code; UI redesign; production/automated ingestion (user-triggered
+ first-run seed only); company→country mapping; valuation-model integration;
paid/proprietary sources; modifying CVM/B3 data or `src/kpi_engine.py`; changing
sector classification; modifying legacy/inactive code (`apps/web` stays removed);
monthly Ember data (deferred v2); migrating existing company KPIs into the new
catalog (compatibility path only — §17.5).

---

## 15. Open questions for João

Folded into §16 (each decision carries a recommendation + open question).

---

## 16. Proposed v1 decisions (recommendation · rationale · open question)

1. **Annual only?** → **Recommend yes (annual only).** OWID is annual; monthly
   needs Ember key + larger footprint. *Open:* any near-term need for monthly BR
   demand/price context?
2. **Brazil + peers vs global?** → **Recommend Brazil + a small curated peer set**
   (e.g. BR, plus a handful: US, CN, an EU aggregate, CL, AR). Smaller footprint,
   targeted comparability, less Ember rate-limit exposure later. *Open:* which
   exact peer list?
3. **Ember in v1?** → **Recommend NO direct Ember in v1** — OWID already carries
   Ember-derived electricity annually. Integrate Ember only after Phase-2 field
   verification (for capacity/monthly/freshness). *Open:* is capacity wanted badly
   enough to prioritize the Ember key now?
4. **Defer installed capacity?** → **Recommend defer** (`blocked_by_source_
   verification`); OWID has none, Ember fields unverified. *Open:* capacity in v1
   if a verified public source is confirmed?
5. **Conflicts: both values or canonical+flag?** → **Recommend canonical (OWID)
   displayed + store both + conflict flag/badge.** Clean default, full audit.
   *Open:* show both side-by-side in the drilldown by default?
6. **Separate `energy_kpis.db` vs existing DB?** → **Recommend separate file.**
   Decouples macro registry from CVM financials, independent refresh, zero
   migration risk. *Open:* any cross-DB join need that argues for one file?
7. **UI home: Energy sector pages, Macro page, or both?** → **Recommend start
   inside Energy Utilities sector pages** (a "Macro / Country" tab), with the
   registry designed so a future top-level Macro page reuses the same catalog
   query layer. *Open:* does João want a standalone Macro page in v1?

---

## 17. Centralized Sector KPI Registry / Catalog (architecture)

Energy Utilities country KPIs are the **first tenant** of a shared registry, not a
one-off. The registry is the single place to **discover, filter, validate,
refresh, export, and display** KPIs across sectors and sources.

### 17.1 Why centralize
Today KPI definitions live inline in `src/kpi_engine.py` (`_KPI_CATALOG` tuples)
and are consumed directly by readers/exporters — no shared discovery, no source/
geography metadata, no per-KPI data-quality/availability state. Adding macro KPIs
the same ad-hoc way would scatter definitions across engine, read service,
bridge, frontend, and exporter. A registry removes duplication and makes
"which KPIs exist for X?" a query, not a code read.

### 17.2 Five metadata layers (keep separate)
1. **KPI definition / catalog metadata** — *what a KPI is* (slow-changing):
   id, names, type, macro_category, unit, sources, use cases, policies.
   → `kpi_catalog`.
2. **KPI values / time series** — observations by entity×period×source.
   → `country_kpi_values` (and future `company_kpi_values`, `market_kpi_values`).
3. **Source metadata** — name, priority, license, cadence, schema version,
   retrieval method, caveats, raw-snapshot lineage. → `kpi_sources`,
   `source_snapshots`.
4. **Data-quality metadata** — missing, fallback, conflict, stale, validation
   flags, audit notes. → `data_quality_checks` + status columns on values.
5. **UI / export mapping** — which KPIs appear in dashboards/details/tooltips/
   Excel/internal checks. → `dashboard_group`, `dashboard_priority`,
   `excel_export_priority`, `audit_required` columns on `kpi_catalog`.

### 17.3 Unified catalog field model (registry superset)

| Field | Purpose |
|---|---|
| `kpi_id` | Stable namespaced PK, e.g. `energy_utilities.country.elec_hydro_share`. |
| `canonical_name` | Stable internal name (cross-source). |
| `display_name` | UI label (English). |
| `description` | Analyst definition. |
| `domain` | `financial` \| `market` \| `macro` \| `operating` \| `regulatory` \| `commodity` \| `credit` \| `valuation` \| `derived`. |
| `sector` / `subsector` | Sector taxonomy (Energy Utilities / Power Generation…). |
| `kpi_type` | `mix_share`/`intensity`/`volume`/`growth`/`ratio`/… |
| `macro_category` | Grouping (electricity_mix, emissions, …). |
| `geography_type` | `country`/`region`/`world`/`company`/`global`. |
| `entity_type` | `country` \| `company` \| `sector` \| `market`. |
| `entity_scope` | e.g. `BR` / `ALL_COUNTRIES` / `B3_LISTED`. |
| `company_relevance` | `none`/`context`/`direct` — usefulness at company level. |
| `country_relevance` | `none`/`context`/`direct`. |
| `unit` | Canonical unit. |
| `frequency` | `annual`/`monthly`/`quarterly`. |
| `default_period_type` | `calendar_year`/`fiscal_year`/`ltm`/`month`. |
| `primary_source` | `OWID`/`EMBER`/`CVM`/`B3`/`YFINANCE`/`DERIVED`. |
| `fallback_sources` | Ordered list. |
| `source_priority` | Int. |
| `source_field` | Original field per source. |
| `calculation_method` | `direct`/`derived_yoy`/`derived_trend`/formula. |
| `is_raw_source_metric` / `is_derived_metric` | Booleans. |
| `dashboard_group` / `dashboard_priority` | UI grouping / `lead\|secondary\|detail_only\|not_in_v1_dashboard`. |
| `excel_export_priority` | `required\|optional\|none`. |
| `modeling_use_case` | Equity/credit/IB/valuation note. |
| `audit_required` | Boolean. |
| `data_quality_status` | `ok\|partial\|missing\|fallback_used\|conflict\|stale`. |
| `availability_status` | `available\|partial\|unavailable`. |
| `source_verification_status` | `verified\|pending\|blocked`. |
| `refresh_policy` / `staleness_policy` | Cadence + stale threshold. |
| `owner_module` | e.g. `energy_kpi`, `kpi_engine`, `market_cap`. |
| `notes` | Free text. |

Definition fields live on `kpi_catalog`; volatile state
(`data_quality_status`, `last_updated`) is computed/joined from the values +
DQ layers, not hand-edited.

### 17.4 Filtering & retrieval model (future read service)
A shared catalog query layer (e.g. `KpiCatalogService` in `src/`, surfaced via a
`get_kpi_catalog(filters)` bridge method + `apps/api`) returns KPI definitions
and/or values filtered by: `sector`, `subsector`, `kpi_type`, `macro_category`,
`entity_type`, `geography_type`, `country`, `company`, `source`, `frequency`,
`unit`, `dashboard_group`, `dashboard_priority`, `availability_status`,
`data_quality_status`, `source_verification_status`.

It answers: which KPIs exist for Energy Utilities? macro vs company-level? by
source (OWID/Ember/CVM/B3/yfinance)? available for Brazil? for a given dashboard?
which export to Excel? lead vs detail-only? blocked by verification? stale/
fallback/conflicted?

**Rule:** dashboards and the exporter request KPI **groups** from this layer.
**No frontend-hardcoded KPI lists** and no duplicated KPI definitions across
modules. Excel export set = catalog query on `excel_export_priority`.

### 17.5 Relationship to existing `src/kpi_engine.py` (compatibility path)
- **Keep `kpi_engine.py` stable.** It stays the authority for company financial
  KPI *computation* from CVM accounts. No breaking change, no forced migration.
- **Registry is additive and describes, it does not recompute.** The registry
  holds *metadata*; the engine still produces company KPI *values*.
- **Phased convergence:**
  1. v1 — registry holds **only** macro/country KPIs under namespace
     `energy_utilities.country.*`. Engine untouched.
  2. v2 — optionally register existing company KPIs as catalog **entries**
     (`owner_module='kpi_engine'`, `entity_type='company'`,
     `domain='financial'`) that *point to* the engine as their producer — metadata
     only, engine still computes. This makes company KPIs discoverable/filterable
     without rewriting them.
  3. Later — unify read access behind the catalog query layer so dashboards fetch
     both company and macro KPIs through one interface.
- **Namespacing:** start Energy Utilities as a separate registry namespace
  `energy_utilities.country.*`, preserving a clean path to a unified catalog. No
  existing CVM KPI calculation changes.

---

## 18. Implementation Readiness Checklist

Coding begins only when **all** are true (✅/⏳ tracks current state):

- ⏳ **OWID fields verified** — ✅ core electricity/energy/emissions/trade columns
  verified vs codebook (§6.1). Remaining: confirm per-country year-start coverage.
- ⏳ **Ember fields verified or explicitly deferred** — API + datasets verified;
  **field names NOT verified** → capacity `blocked_by_source_verification`; v1
  ships **OWID-only** (Ember deferred). Decision §16.3.
- ⏳ **v1 KPI catalog approved** — §5 (21 rows, 9 required, 1 blocked) pending
  João sign-off.
- ⏳ **Local storage decision approved** — separate `energy_kpis.db` recommended
  (§16.6).
- ⏳ **Country scope approved** — Brazil + curated peers recommended (§16.2);
  peer list open.
- ⏳ **Annual/monthly scope approved** — annual-only recommended (§16.1).
- ⏳ **Dashboard entry point approved** — Energy sector "Macro/Country" tab
  recommended (§16.7).
- ⏳ **Excel export shape approved** — four-tab, priority-driven (§11).
- ⏳ **Validation rules approved** — §9 check set.
- ⏳ **Tests identified** — `tests/energy_kpi/` fixtures: ingest, merge/priority,
  DQ flags, offline-read, Excel formatting (§12 Phase 8).
- ⏳ **Registry namespace + kpi_engine compatibility approved** — `energy_
  utilities.country.*`; engine untouched (§17.5).

---

## 19. Acceptance criteria (initiative)

- [x] Canonical planning `.md` exists and remains canonical.
- [x] Contains a clear v1 KPI catalog table (§5) — each KPI has source, unit,
      frequency, audit notes, `v1_status`.
- [x] OWID field names verified, **not guessed** (§6.1).
- [x] Ember limitations explicit; capacity not assumed (blocked) (§6.2, §5).
- [x] Local-first / offline / reproducibility / low-footprint preserved (§7).
- [x] Dashboard, Excel, validation, audit addressed (§§9–11).
- [x] Implementation readiness stated (§18).
- [x] Centralized Sector KPI Registry planned (§17): centralization, filtering by
      type/source/sector, Energy Utilities as first tenant, `kpi_engine.py`
      coexistence, no-duplication consumption, required catalog fields.
- [x] No implementation code changed (docs-only).
