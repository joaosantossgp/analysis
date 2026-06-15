# Energy Utilities Distribution Ingestion

Active reference for the local-first ANEEL electricity distribution module.

## Runtime Path

- UI: `apps/desktop-web/src/components/indicators/distribution/DistributorExplorer.tsx`
- Frontend facade: `apps/desktop-web/src/lib/api/distribution.ts`
- Desktop bridge: `desktop/bridge_api/distribution.py`
- Python core: `src/energy_kpi/distribution/`
- Local database: `energy_kpis.db`, resolved through `src/platform/settings.py`

Reads are offline-only. Manual refresh downloads ANEEL open-data resources into
the local raw energy cache and publishes normalized facts into the Distribution
tables.

## Refresh And Diagnostics

Manual refresh is single-flight in the desktop bridge: duplicate starts return
`already_running` while the existing job continues. The refresh path reuses the
latest valid local snapshot unless `force` is requested, so cached reruns do not
download the same ANEEL file again.

Each source step is logged in `energy_source_refresh_log` with download, parse,
publish, aggregate, and SQLite lock-wait durations; source, parsed, canonical,
and published row counts; conflict and unresolved-identity counts; and optional
process RSS/CPU diagnostics. The UI exposes these logs in the Distribution Data
Health panel.

Fact publishing uses bounded insert batches and avoids materializing whole fact
frames as Python lists. SQLite writes are scoped to short source-level
transactions, and aggregate rebuild runs after source publication so reads keep
using the last valid persisted data if a later source fails.

## UI Contract

The Distribution panel supports distributor and economic-group modes. Both modes
read persisted aggregate series from the bridge and render:

- a historical SVG chart for Market, Balance, Quality, Tariffs, Delinquency,
  and MMGD metrics with per-point period/value tooltips;
- an audit table using the same aggregate rows as the chart;
- loading, error, empty, running, success, and failed refresh states.

Null aggregate values remain null through the bridge and render as gaps or
dashes. The UI must not coerce missing values to zero.

## Parser Contract

Each parser follows the same boundary contract:

1. Read the official CSV or Parquet resource.
2. Map explicit source columns to parser-canonical columns.
3. Validate required canonical columns before any Polars expression references
   them.
4. Normalize CNPJ as text, preserving leading zeros through 14-digit padding.
5. Publish only normalized facts with deterministic source row hashes.

Missing required source/canonical columns raise `DistributionSchemaError` with
the dataset, stage, missing canonical columns, mapped source columns, available
columns, resource file, and parser version.

Extra source columns are treated as schema drift and do not block ingestion
unless they replace a required field.

## Source CNPJ Fields

Supported distributor CNPJ aliases are source-specific and explicit:

- SAMP Mercado: `NumCNPJAgenteDistribuidora`
- SAMP Balanco: `NumCPFCNPJ`
- DEC/FEC actuals, limits, and compensations: `NumCNPJ`
- Tarifas de Aplicacao: `NumCNPJDistribuidora`, legacy `NumCNPJ`, or canonical
  `raw_cnpj`
- Inadimplencia: `NumCNPJ`
- MMGD projects: `NumCNPJDistribuidora`

The tariff parser also supports the current ANEEL tariff dimensions observed in
real cached files, including `DscREH`, `SigAgente`, `DscSubGrupo`,
`DscModalidadeTarifaria`, `DscClasse`, `DscSubClasse`, `DscUnidadeTerciaria`,
and already-canonical intermediate columns such as `tariff_base`,
`consumer_detail`, `tariff_period`, `tusd_raw`, and `te_raw`.

## Current Validation Coverage

Regression tests cover tariff CSV and Parquet inputs, formatted CNPJ,
unformatted CNPJ, leading-zero CNPJ, null CNPJ, invalid CNPJ, canonical input,
missing CNPJ aliases, unknown extra columns, and column-order independent
mapping.

Representative real cached ANEEL files have been smoke-tested for SAMP Balanco,
SAMP Mercado 2024, SAMP Mercado 2025, SAMP Mercado 2026, DEC/FEC actuals,
DEC/FEC limits, DEC/FEC compensations, and tariffs.
