# Energy/Utilities Driver Pilot Contract

Status: approved by João on 2026-07-11.

Issue: #352.
Epic: #347.
Task type: Decision only. This document does not authorize implementation.

## Approved pilot question

Is the Brazilian power system becoming structurally tighter or looser, which
observable drivers explain the change, and which types of electricity companies
are most exposed?

Approval source: Joao's 2026-07-11 Codex prompt for issue #352. The GitHub
issue had no prior approval comment when work started, so this decision record
and the issue execution note preserve the approval source.

Final approval: João approved the final five-family matrix in PR #357 on
2026-07-11. This approval authorizes merging this Decision record. It does not
authorize implementation, UI changes, bridge methods, database changes,
importers, aggregation formulas, alerts, scoring, forecasts, valuation, thesis,
or implementation issues.

Approval constraints that remain active:

- Capacity and firm-supply headroom remains blocked pending a separate approved
  aggregate contract.
- Complete forward-looking system adequacy remains outside this pilot.
- Company handoffs remain exposure hypotheses only.

## Boundaries

In scope:

- Brazilian electricity system and SIN.
- Sector/system-first analysis before company conclusions.
- ONS, CCEE, EPE, and ANEEL evidence, with current repository state verified
  before selecting each driver.
- Only material drivers required by the approved question.
- Company handoffs only as areas for further investigation.

Out of scope:

- ANP and fuel distribution.
- Company-specific KPIs.
- Plant, parcel, or asset-level analysis.
- Alerts, factor scoring, forecast implementation, valuation, thesis, UI,
  bridge methods, database schema, importers, or ingestion changes.
- Proven company financial causality. This contract can identify exposure
  hypotheses and future modeling links, but it cannot claim financial impact.

## Analytical horizon

This pilot supports historical diagnosis, current-condition diagnosis, and an
assessment of whether observed SIN conditions have been becoming tighter or
looser.

This pilot does not support a complete forward-looking system-adequacy forecast
or a definitive long-term structural conclusion. A future forward-looking
extension requires a separately approved contract covering at least demand
outlook, capacity expansion pipeline, expected commissioning dates, delays and
cancellations, retirements, comparable firm-supply measures, scenario
assumptions, and temporal alignment between demand, capacity, and firm-supply
evidence.

EPE demand and expansion outlooks remain deferred from this pilot because they
do not yet have a verified local read model or user-facing workflow, but they
are required inputs for that future forward-looking extension.

## Repository baseline

Verified current implementation:

- Active runtime: Vite desktop app in `apps/desktop-web` served by the
  pywebview bridge, per `AGENTS.md` and `docs/architecture.md`.
- Active Indicator route: `/indicators`, per
  `apps/desktop-web/src/App.tsx` and `docs/reference/indicators-module.md`.
- SIN Power System surface: `apps/desktop-web/src/components/indicators/SINKpiPanel.tsx`.
- SIN bridge methods: `get_sin_kpi_dashboard`, `get_sin_kpi_series`,
  `get_sin_kpi_health`, and `refresh_sin_kpis` in
  `desktop/bridge_api/energy.py`.
- SIN sources and catalog: `src/energy_kpi/sin_catalog.py`,
  `src/energy_kpi/sin_ingest.py`, `src/energy_kpi/sin_refresh.py`, and
  `src/energy_kpi/read.py`.
- Local Energy database: `energy_kpis.db`, with `kpi_catalog`,
  `kpi_sources`, `source_snapshots`, `subsystem_dimension`, and
  `subsystem_kpi_values` in `src/energy_kpi/schema.py`.
- ANEEL Distribution surface: `Sectors -> Distribution`, with bridge methods
  in `desktop/bridge_api/distribution.py`, local facts/aggregates in
  `src/energy_kpi/schema.py`, and reference contract in
  `docs/reference/energy-utilities-distribution.md`.
- CCEE/ANEEL generation and plant source foundation: `ccee_plant_parcels`,
  `ccee_plant_parcel_monthly`, `ccee_plant_parcel_hourly`,
  `plant_parcel_daily_generation_mart`, and related source logs in
  `src/energy_kpi/schema.py`; source definitions in
  `src/energy_kpi/plant_parcel_ingest.py`.
- Indicator Library boundary: default library rows must be openable without
  selecting company, distributor, plant, parcel, asset, ticker, fuel product,
  state, or economic group, per `docs/reference/indicators-module.md`.

Known gaps:

- EPE electricity consumption by class/region/subsystem is prepared for later
  in `docs/reference/energy-utilities-sin-kpis.md`, but not implemented as a
  verified local read model.
- CCEE PLD is partial/source-risky because public direct access may reject the
  runtime request.
- ONS directional Intercambio is a future connector; the current SIN module has
  only `val_intercambio` as a net interchange proxy.
- Regulatory events and tariff-review calendars are product-direction concepts
  without a verified current workflow.
- Company-level impact requires exposure mapping and later modeling. Existing
  asset/distributor mappings are investigation aids, not proof of financial
  causality.

## Analytical families

The pilot uses five analytical families because these are the smallest material
set needed to answer the approved question. The count is not a target. The
first three families are explanatory drivers, the fourth is a
confirmatory/outcome signal, and the fifth is a required future capability that
is not implementation-ready until an aggregate contract is approved.

| Analytical family | Analytical role | Implementation readiness | Source/provider | Grain | Main caveat |
| --- | --- | --- | --- | --- | --- |
| SIN load and demand pressure | Explanatory driver | Eligible for implementation planning after final approval from existing SIN evidence | ONS | SIN subsystem by timestamp | Demand pressure needs supply and hydro context before interpretation. |
| Generation supply and mix | Explanatory driver | Eligible for implementation planning after final approval from existing SIN evidence | ONS | SIN subsystem/source by timestamp | Mix shares are local calculations and do not prove company impact. |
| Hydro buffer and inflow | Explanatory driver | Eligible for implementation planning after final approval from existing SIN evidence | ONS | SIN subsystem by timestamp | Hydrology explains system conditions, not company financial causality. |
| System price confirmation | Confirmatory/outcome signal | Eligible for implementation planning after final approval for ONS CMO; CCEE PLD remains partial/source-risky | ONS and CCEE | SIN subsystem/submarket by timestamp | Price must not be used circularly as both cause and proof of tightness. |
| Capacity and firm-supply headroom | Required future capability | Implementation blocked pending an approved aggregate contract | ANEEL and CCEE | Plant and parcel evidence only; no approved system aggregate | MW and MWmed cannot be added or directly compared; no headroom formula is approved. |

## Analytical family contract

### 1. SIN load and demand pressure

Analyst question answered: Is the SIN/subsystem load trend making the power
system structurally tighter or looser?

Materiality: load is the demand side of the tightness question. Without a load
series, capacity, generation, hydrology, and price cannot be interpreted.

Source class and provider: official external dataset, ONS.

Entity and grain: SIN subsystem (`S`, `SE_CO`, `NE`, `N`) by timestamp.

Unit and scale: `MWmed`.

Frequency and historical coverage: hourly observations for the years refreshed
locally by the SIN refresh job. Default refresh attempts current and previous
calendar year.

Local database/store/mart: `energy_kpis.db`; `subsystem_kpi_values` keyed by
`energy_utilities.sin.load_mwmed`, `reference_datetime`, and
`subsystem_code`; source metadata in `kpi_sources` and `source_snapshots`.

Transformation or formula: direct ONS `val_carga` from
`balanco_energia_subsistema`.

Freshness: latest local `reference_datetime` and source snapshots from the SIN
health/read path.

Offline availability: reads are offline-only after refresh. Opening the
dashboard must not call ONS.

Missing, partial, stale, and failure behavior: missing local rows render as no
cached observations; stale is inferred from local latest reference versus
expected recency; failed refresh remains visible through SIN source status and
refresh error; partial refresh can still leave ONS data readable.

Sector interpretation: rising load, especially if paired with weak hydro
buffers, high thermal dispatch, or confirmatory high price signals, points
toward a tighter system. Flat or falling load with stable supply and lower
price confirmation points toward a looser system.

Exposed business models or company types: distribution companies through demand
and regulated market volume; generators and integrated utilities through system
balance and price sensitivity. This is exposure, not proven earnings impact.

Evidence versus hypothesis versus modeled causality: load observations are
evidence. Company exposure is a hypothesis. Revenue, margin, or cash-flow
impact requires future company mapping and modeling.

Possible future Critical Factors / forecast connection: system load growth can
become a sector driver feeding distributor market-volume assumptions or
generator dispatch/price scenarios.

Correct product workspace: default Indicator Library and Energy Power System;
company follow-up belongs in Company Workspace only after exposure mapping.

### 2. Generation supply and mix

Analyst question answered: Which generation sources are meeting system demand,
and is the mix shifting toward tighter or looser operation?

Materiality: supply mix shows whether demand is being met by lower-cost hydro
and renewables or by higher-cost thermal generation and interchange pressure.

Source class and provider: official external dataset, ONS.

Entity and grain: SIN subsystem by timestamp and source family.

Unit and scale: `MWmed` for generation; percent for local mix shares.

Frequency and historical coverage: hourly observations for refreshed years.

Local database/store/mart: `energy_kpis.db`; `subsystem_kpi_values`; catalog
records in `kpi_catalog` for hydro, thermal, wind, solar, total generation, and
mix share KPIs.

Transformation or formula:

- direct ONS fields: `val_gerhidraulica`, `val_gertermica`, `val_gereolica`,
  `val_gersolar`;
- total generation = hydro + thermal + wind + solar;
- mix share = source generation / total generation.

Freshness: latest local observation and snapshot metadata from the SIN read
path.

Offline availability: local cached reads only.

Missing, partial, stale, and failure behavior: no source row means missing; a
partial source refresh should not erase previously readable cached values;
derived shares are unavailable when total generation is missing or zero.

Sector interpretation: higher thermal share during load or hydrology stress is
a tightness signal. Higher renewable/hydro contribution can loosen the system
if it is reliable and not offset by lower storage or higher demand.

Exposed business models or company types: hydro generators, thermal generators,
wind/solar generators, integrated utilities, and traders/retailers exposed to
system prices. Company-level effect is not proven by the system mix alone.

Evidence versus hypothesis versus modeled causality: source/mix observations
are evidence. Exposure by business model is a hypothesis. Company impact needs
ownership mapping, contracted/uncontracted position, and model assumptions.

Possible future Critical Factors / forecast connection: generation mix can
support company driver assumptions for dispatch, contracted energy strategy,
and price scenarios after exposure rules are approved.

Correct product workspace: Indicator Library and Energy Power System for
system/subsystem views; Generation/Asset workflow only for later entity-level
investigation.

### 3. Hydro buffer and inflow

Analyst question answered: Is hydro flexibility improving or deteriorating?

Materiality: Brazil's power system remains materially sensitive to hydrology.
Stored energy and inflows explain whether the system has flexibility before it
needs more thermal dispatch or price rationing.

Source class and provider: official external dataset, ONS.

Entity and grain: SIN subsystem by date.

Unit and scale: stored energy in `MWmes` and `%`; ENA in `MWmed` and `% MLT`.

Frequency and historical coverage: daily observations for refreshed years.

Local database/store/mart: `energy_kpis.db`; `subsystem_kpi_values`; catalog
records for `ear_stored_mwmes`, `ear_stored_pct`, `ena_gross_mwmed`,
`ena_gross_pct_mlt`, `ena_storable_mwmed`, and
`ena_storable_pct_mlt`.

Transformation or formula: direct ONS fields from `ear_diario_subsistema` and
`ena_diario_subsistema`.

Freshness: latest local daily reference date and source snapshot metadata.

Offline availability: local cached reads only.

Missing, partial, stale, and failure behavior: missing daily rows are
unavailable; stale daily data must be shown as stale rather than reused as
current; failed refresh preserves the last valid local state and exposes the
refresh error.

Sector interpretation: low or falling storage and weak ENA indicate a tighter
system and greater need for thermal dispatch or imports/interchange. High or
recovering storage and ENA indicate looser hydro conditions.

Exposed business models or company types: hydro generators, integrated
utilities with hydro exposure, thermal generators that benefit from dispatch,
and retailers/traders exposed to spot prices. Direct company effect is not
proven without portfolio and contract exposure.

Evidence versus hypothesis versus modeled causality: ONS hydrology values are
evidence. Business-model exposure is a hypothesis. Financial impact requires a
Critical Factor or forecast model.

Possible future Critical Factors / forecast connection: hydrology can become a
company Critical Factor for hydro-heavy utilities and a forecast input for PLD,
thermal dispatch, and margin scenarios.

Correct product workspace: Indicator Library and Energy Power System; company
handoff to Company Workspace after approved exposure mapping.

### 4. System price confirmation

Analyst question answered: Do price and marginal-cost signals confirm system
tightness or looseness?

Materiality: price signals summarize observed market and dispatch outcomes
after load, hydrology, generation availability, and supply conditions have
already been evaluated as explanatory drivers.

Source class and provider: official external datasets, ONS for CMO and CCEE for
PLD.

Entity and grain: SIN subsystem/submarket by timestamp.

Unit and scale: `R$/MWh`.

Frequency and historical coverage: ONS CMO is semi-hourly; CCEE PLD is hourly
where source access succeeds.

Local database/store/mart: `energy_kpis.db`; `subsystem_kpi_values` for
`cmo_brl_mwh` and `pld_brl_mwh`; source metadata in `kpi_sources` and
`source_snapshots`.

Transformation or formula: CMO is direct ONS `val_cmo`; PLD is CCEE
`PLD_HORA` mapped to the SIN subsystem code.

Freshness: latest local reference timestamp; CCEE PLD status must preserve the
source-risk caveat.

Offline availability: local reads only after successful refresh.

Missing, partial, stale, and failure behavior: ONS CMO can be available while
CCEE PLD is missing or failed. CCEE PLD remains explicitly
partial/source-risky. PLD access failure must be visible and must not silently
substitute another value. Skipped or failed PLD does not invalidate ONS CMO
evidence.

Sector interpretation: high or rising CMO/PLD can support a tighter-system
interpretation when load, weak hydrology, generation availability, and supply
conditions independently point that way. Low or falling CMO/PLD can challenge a
tightness interpretation or support a looser interpretation when supply
conditions are adequate. Price must not be used circularly as both the cause
and proof of system tightness.

Exposed business models or company types: merchant/uncontracted generators,
thermal generators, hydro generators exposed to spot/GSF effects, traders,
retailers, and integrated utilities. Exposure depends on contracts and
portfolio position.

Evidence versus hypothesis versus modeled causality: CMO and PLD are evidence
of observed price outcomes, not primary causal drivers. Exposure by company
type is a hypothesis. Company margin effect is modeled causality and is not
authorized here.

Possible future Critical Factors / forecast connection: CMO/PLD can become a
pricing confirmation signal, forecast output check, or scenario input after
source reliability, exposure, and contract-position assumptions are approved.

Correct product workspace: Indicator Library and Energy Power System. CCEE PLD
must remain visibly partial/source-risky until reliability is improved.

### 5. Capacity and firm-supply headroom

Analytical role: required driver capability -- implementation blocked pending
an approved aggregate contract.

Analyst question answered: In a future approved extension, is structural supply
capacity expanding enough to explain a looser system, or is demand outpacing
comparable firm supply?

Materiality: structural tightness is not only current dispatch. The analyst
will need a capacity and firm-supply lens to separate temporary hydrology or
price outcomes from a persistent supply-demand imbalance, but the current
repository has plant- and parcel-grain evidence rather than an approved
system-level headroom metric.

Source class and provider: official external datasets, ANEEL and CCEE.

Entity and grain: CEG plant and CCEE plant parcel. Plant and parcel records
remain investigation handoffs only. They must not be aggregated into a system
metric without approved entity deduplication and grain rules.

Unit and scale: installed capacity in `MW`; physical guarantee in `MWmed`;
generation in `MWmed`, `MWh`, or derived `GWh` depending on read path.
Installed capacity in MW is not firm supply. Physical guarantee in MWmed is
not operational availability. MW and MWmed must not be added or directly
compared.

Frequency and historical coverage: ANEEL SIGA plant registry is
monthly/daily; CCEE plant parcel monthly data is annual/monthly by source
resource; CCEE hourly generation is monthly and large.

Local database/store/mart: `energy_kpis.db`; `aneel_siga_plants`,
`ccee_plant_parcels`, `ccee_plant_parcel_monthly`,
`ccee_plant_parcel_hourly`, `plant_parcel_daily_generation_mart`,
`plant_parcel_hourly_preview_mart`, `plant_ceg_hourly_generation_mart`,
`plant_parcel_source_submarket_monthly_mart`, and
`energy_mart_builds`.

Transformation or formula: capacity normalized from ANEEL kW fields to MW
where exposed by plant metrics; CCEE generation calculations use existing
monthly/daily/hourly read paths and mart outputs. No system headroom formula is
approved by this decision. Commissioning, retirement, delay, and cancellation
treatment must be defined before any aggregate is calculated.

Freshness: source status and mart status from existing plant parcel source
status and Energy mart diagnostics.

Offline availability: local reads only after source import/refresh and mart
build. Broad hourly reads must use existing bounded marts or explicit
entity/month/date-window guardrails.

Missing, partial, stale, and failure behavior: missing source rows or stale
marts make plant/parcel evidence unavailable or partial; large raw hourly data
must not be scanned for broad system views; CCEE access blocks and manual
import fallbacks must remain visible. No system headroom status may be reported
until temporal alignment between demand, capacity, and firm-supply evidence is
approved.

Sector interpretation: capacity additions and comparable firm-supply measures
may eventually help explain structural loosening when they expand faster than
load under approved temporal and grain rules. The current evidence cannot prove
system headroom. If capacity expansion is intermittent, concentrated, delayed,
cancelled, retired elsewhere, or not matched by comparable firm supply, the
system may remain tight despite nominal MW additions.

Exposed business models or company types: generators by source type,
integrated utilities with generation portfolios, and companies with mapped
plants. This is an investigation handoff, not a company KPI.

Evidence versus hypothesis versus modeled causality: source capacity and
generation records are evidence at plant/parcel grain. System headroom is a
future calculated sector metric blocked pending an approved aggregate contract.
Company exposure is a hypothesis until ownership mapping and forecast
assumptions are approved.

Possible future Critical Factors / forecast connection: capacity/flexibility
can feed company Critical Factors for portfolio mix, availability, contracted
energy, and future dispatch only after the aggregate contract, exposure mapping,
and model contract are approved.

Correct product workspace: Sector Workbench with Generation/Asset handoff. Do
not add plant/parcel rows to the default Indicator Library. No default
Indicator Library metric may be created from this capability yet.

## Company exposure handoffs

These are not implementation requirements and do not prove financial impact.

| Exposure type | Why it matters | Correct handoff | Required caution |
| --- | --- | --- | --- |
| Hydro-heavy generators | Sensitive to hydrology, storage, ENA, GSF, and spot prices. | Company Workspace / future Critical Factors after portfolio exposure mapping. | GSF is not verified as a current source contract in this pilot. |
| Thermal generators | Benefit from dispatch and confirmed price outcomes, but depend on fuel, contracts, availability, and merit order. | Generation/Asset workflow, then Company Workspace. | Fuel cost and dispatch economics are not implemented here. |
| Wind/solar generators | Exposed to capacity growth, generation mix, curtailment, and price profile. | Generation/Asset workflow. | Plant/parcel analysis is excluded from the pilot contract. |
| Distribution utilities | Exposed to demand, losses, MMGD penetration, tariffs, service quality, and regulatory pass-throughs. | Distribution workspace and Company Workspace. | Distribution metrics are entity-dependent and do not enter the default Indicator Library. |
| Integrated utilities | Exposed through both generation and distribution portfolios. | Company Workspace after asset/distributor mapping review. | Do not infer consolidated impact from system indicators alone. |
| Retailers/traders/free-market exposure | Sensitive to PLD/CMO, contract position, and customer load. | Future Company Workspace / Model Workspace. | Contract position data is not available in the verified repository baseline. |

## Rejected or deferred drivers

| Driver or source | Decision | Reason |
| --- | --- | --- |
| EPE electricity consumption by class/region/subsystem | Deferred from this pilot; required for a future forward-looking extension. | Prepared for later in SIN docs, but no verified local read model or user-facing workflow exists. ONS load is sufficient for the first historical/current demand-side pilot. |
| EPE demand and expansion outlook | Deferred from this pilot; required for a future forward-looking extension. | Forward-looking adequacy requires demand outlook, expansion pipeline, expected commissioning dates, delays/cancellations, retirements, comparable firm-supply measures, scenario assumptions, and temporal alignment. |
| ANP fuel distribution | Excluded. | Explicitly outside the approved Brazilian electricity/SIN boundary. |
| Company financial KPIs, leverage, margins, capex | Excluded from this decision. | These belong in Company Workspace and can inform future company Critical Factors, not the sector/system pilot. |
| Plant, parcel, or asset-level drill-down | Excluded from pilot analysis; allowed only as a future investigation handoff. | Explicit exclusion and not openable as default Indicator Library evidence. |
| GSF/MRE company impact | Deferred. | Material for hydro exposure, but no verified current source contract was found for this pilot. |
| Regulatory events and tariff-review calendar | Deferred. | Product direction mentions them, but no verified current source workflow exists. |
| Relative stock performance | Deferred. | Useful for sector review, but not required to answer system tightness; market data is external/unofficial. |
| Sector financial metrics | Deferred. | Useful later, but not needed for the first system-tightness question and would pull company financial analysis into a sector decision. |
| Alerts, scoring, forecasts, valuation, thesis | Excluded. | Explicitly outside this Decision task and not authorized by this document. |

## Product ownership rules

- Default Indicator Library: system/subsystem drivers that can be opened
  without selecting a company, plant, parcel, distributor, state, product,
  ticker, or economic group.
- Sector Workbench / Energy Power System: interpretation of load, generation,
  hydrology, system price confirmation, and future approved sector aggregates.
- Distribution workspace: distributor/economic-group metrics such as billed
  energy, tariffs, losses, DEC/FEC, delinquency, and MMGD.
- Generation/Asset workflow: plant, parcel, CEG, capacity, and asset-level
  generation evidence.
- Company Workspace: issuer-level financials, company-specific operational
  metrics, exposure notes, and future Critical Factors.
- Future Model Workspace: forecasts, scenario assumptions, causal financial
  impact, and sensitivity analysis.

## Acceptance test for this decision

The pilot is ready for implementation planning only when Joao reviews and
approves:

- the five analytical families and their roles;
- the selected source/provider/grain matrix and implementation-readiness limits;
- the deferred driver list;
- the rule that company handoffs are exposure hypotheses only;
- the rule that this decision does not authorize implementation.

Until that approval is recorded, do not create implementation issues for UI,
bridge methods, database schema, importers, alerts, forecasts, valuation, or
thesis workflows based on this document.
