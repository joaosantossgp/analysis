# Energy/Utilities Source And Driver Readiness Audit

This is the first foundational audit before building Critical Factors,
forecasting, valuation, or thesis workflows for Energy/Utilities.

Goal: identify which Energy/Utilities drivers are source-ready, partial,
prepared, or missing, and decide what should be built next: source/database,
read model, page/workspace, or export/audit behavior.

## Current Source Foundation

Verified from current reference docs:

- SIN subsystem KPIs exist in `energy_kpis.db` with offline reads through
  `get_sin_kpi_dashboard`, `get_sin_kpi_series`, `get_sin_kpi_health`, and
  `refresh_sin_kpis`.
- SIN implemented sources include ONS load, generation by source, stored energy,
  ENA, CMO, and CCEE PLD when public access works.
- CCEE PLD is source-risky and may be partial if public access rejects the
  runtime request.
- ANEEL electricity distribution ingestion exists with local refresh,
  diagnostics, source logs, aggregate rows, charts, detail tabs, and Excel
  export.
- CCEE plant-parcel generation data exists with local source-derived facts and
  rebuildable marts for hot UI reads.
- ANP fuel distribution exists as an implemented managed-ingestion pilot.
- EPE consumption and several ANEEL sources are prepared for later in the SIN
  reference, not implemented as reliable user-facing workflows there.

## Driver Readiness Matrix

| Driver | Current data foundation | Readiness | Next build step |
| --- | --- | --- | --- |
| SIN load / demand | ONS Balanço de Energia nos Subsistemas, local SIN KPIs. | Source-ready for system/subsystem view. | Improve sector page/workspace framing before company linkage. |
| Generation by source | ONS Balanço, local SIN KPIs; CCEE plant/parcel generation for asset-level detail. | Source-ready for system view; partial for company impact. | Map source grain to company/asset ownership before using in company factors. |
| Stored energy | ONS EAR Diário, local SIN KPIs. | Source-ready for hydrology/system risk. | Keep in Power System / Indicator Library; later link to utility exposure manually or through model. |
| ENA / hydrology | ONS ENA Diário, local SIN KPIs. | Source-ready for system risk. | Same as stored energy; avoid company-specific claims until exposure rules exist. |
| PLD | CCEE PLD hourly when access works; source-risky fallback behavior is documented. | Partial. | Improve source reliability/status labels before using as a monitored factor. |
| CMO | ONS CMO Semi-Horário. | Source-ready as system indicator. | Decide whether PLD or CMO is the primary pricing driver per workflow. |
| Distributor quality | ANEEL distribution module includes DEC/FEC and related distribution KPIs. | Source-ready for distributor/economic-group workspace. | Map distributors to listed companies before company-level factor use. |
| Tariffs | ANEEL distribution tariff parser and UI contract exist. | Partial/source-ready depending entity mapping. | Audit tariff metric coverage and company ownership mapping. |
| Losses / delinquency / MMGD | ANEEL distribution module includes relevant metrics. | Source-ready for distribution workspace; partial for company factor use. | Define which metrics matter for utilities and how they affect revenue/margins. |
| Plant/parcel generation | CCEE plant-parcel facts and marts exist. | Source-ready for asset workspace. | Strengthen plant/company ownership mapping and source freshness display. |
| Capacity / plants | Plant/parcel catalog exists around generation workflows; ANEEL SIGA is prepared later in SIN docs. | Partial. | Confirm canonical capacity source and ownership mapping before company factors. |
| Regulatory events / tariff review calendar | Mentioned in product direction, but no verified current workflow found in this audit. | Missing. | Define source contract before UI. |
| EPE consumption by class/region/subsystem | Prepared for later in SIN docs. | Prepared, not implemented. | Build source ingestion/read model before sector use. |
| Company leverage | Company financial indicators exist in Company Workspace from CVM statements. | Source-ready for issuer financial view. | Keep in Company Workspace; later link as a financial critical factor. |
| Capex vs plan | CVM statements may expose historical capex/cash-flow evidence, but plan comparison was not verified. | Partial/manual-only. | Define source for plan/budget before factor status. |

## Product Conclusions

Energy/Utilities has enough data to improve sector/source readiness now, but not
enough to build a strong Critical Factors Monitor yet.

The best next product work is:

1. Make the Energy/Utilities driver map explicit.
2. Clarify which drivers are system-level, company-level, distributor-level, or
   plant/asset-level.
3. Improve source status and grain labels near existing Energy views.
4. Strengthen company/asset ownership mapping before claiming company impact.
5. Only then design company-specific Critical Factors.

## Workspace Ownership

| Driver type | Correct home now |
| --- | --- |
| SIN load, stored energy, ENA, CMO, PLD, generation mix | Indicator Library / Energy Power System |
| Distributor quality, tariffs, losses, delinquency, MMGD | Energy Distribution |
| Plant/parcel generation and capacity | Energy Generation / Asset workspace |
| Company leverage, margins, debt, financial KPIs | Company Workspace |
| Regulatory events and tariff-review calendar | Missing source contract |
| Forecast assumptions and factor impact | Future Model / Critical Factors |

## Recommended Next Steps

### Step 1: Source/Driver Labels In Existing Energy Views

Audit the current Energy pages and ensure each visible metric makes clear:

- source;
- unit;
- frequency;
- geography/entity grain;
- latest period;
- refresh status;
- partial/source-risk caveat.

Do not add a new dashboard. Improve the existing pages where the data already
lives.

### Step 2: Company/Asset Ownership Map

Before company-level factors, verify how distributor, plant, parcel, and
economic-group records link to listed CVM companies.

Required outputs:

- mapped / unmapped counts;
- manual override behavior;
- source of ownership mapping;
- timestamp;
- confidence or caveat if confidence is unavailable.

### Step 3: Missing Source Contracts

Define source contracts for the missing or prepared drivers:

- regulatory events;
- tariff review calendar;
- EPE consumption;
- capacity source if ANEEL SIGA is the intended canonical source;
- company plan/budget data for capex vs plan.

### Step 4: Critical Factors Pilot Only After The Above

Pilot Critical Factors only after a specific company has enough source-backed
drivers to support 3 to 7 useful factors.

The pilot should start with a manual factor register linked to existing data,
not automated alerts.

## Non-Goals

- Do not build Critical Factors UI now.
- Do not add valuation, thesis, or forecast pages.
- Do not create empty future tabs.
- Do not add factor scoring.
- Do not imply company-level impact from system indicators without a mapping or
  model.
- Do not move distributor, plant, or fuel product metrics into the default
  Indicator Library.

