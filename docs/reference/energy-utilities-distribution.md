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
