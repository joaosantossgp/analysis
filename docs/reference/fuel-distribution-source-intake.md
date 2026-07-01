# Fuel Distribution Source Intake

Active source dossier for the Energy / Fuel Distribution managed ingestion
pilot.

## Source Family

- Publisher: ANP, Agencia Nacional do Petroleo, Gas Natural e Biocombustiveis.
- Source class: official external dataset.
- Landing page:
  `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/vendas-de-derivados-de-petroleo-e-biocombustiveis`
- Product alignment: GICS Energy coverage, especially Oil & Gas Refining &
  Marketing and fuel distribution market context.
- Import status: implemented as a managed storage/import pilot. The repository
  registers `fuel_distribution_sector_intake` as an implemented managed
  ingestion contract with raw snapshots, cold Parquet detail, and a compact
  SQLite mart layer. Bridge/read contracts are available for summary-first UI
  work; no dedicated UI screen has been added yet.

## Measured CSV Corpus

Measured on 2026-07-01 by streaming the official CSV links from the ANP landing
page with a browser-like user agent. HEAD requests returned 403, so byte sizes
come from ranged/full GET responses. No files were written to the app data
root.

| Dataset | Grain | Period | Rows | Bytes | Unit columns |
|---|---:|---:|---:|---:|---|
| Vendas de derivados petroleo e etanol | state-product-month | 1990-2026 | 94,392 | 5,848,234 | `VENDAS` in m3 |
| Vendas de combustiveis por segmento | state-product-segment-month | 2012-2026 | 42,039 | 2,250,118 | `VENDAS` in m3 |
| Vendas de GLP por tipo de vasilhame | state-vessel-month | 2007-2026 | 12,582 | 790,031 | `VENDAS` in m3 |
| Vendas de oleo diesel por tipo | state-product-month | 2013-2026 | 21,735 | 1,376,135 | `VENDAS` in m3 |
| Vendas de oleo diesel por produtor | state-fuel-month | 2025-2026 | 459 | 23,964 | `VENDAS` in m3 |
| Vendas de biodiesel | origin-region-destination-region-month | 2017-2026 | 1,871 | 70,088 | `Vendas de Biodiesel` in m3 |
| Vendas anuais de asfalto por municipio | municipality-product-year | 1992-2024 | 57,595 | 3,638,729 | `VENDAS` in kg |
| Vendas anuais de etanol hidratado por municipio | municipality-product-year | 1990-2024 | 160,692 | 10,062,933 | `VENDAS` in liters |
| Vendas anuais de gasolina C por municipio | municipality-product-year | 1990-2024 | 180,839 | 12,123,475 | `VENDAS` in liters |
| Vendas anuais de gasolina de aviacao por municipio | municipality-product-year | 1990-2024 | 13,904 | 1,032,212 | `VENDAS` in liters |
| Vendas anuais de GLP por municipio | municipality-product-year | 1992-2024 | 142,290 | 9,158,373 | `P13`, `OUTROS` in kg |
| Vendas anuais de oleo combustivel por municipio | municipality-product-year | 1990-2024 | 25,829 | 2,000,332 | `VENDAS` in kg |
| Vendas anuais de oleo diesel por municipio | municipality-product-year | 1990-2024 | 182,878 | 12,666,750 | `VENDAS` in liters |
| Vendas anuais de querosene de aviacao por municipio | municipality-product-year | 1990-2024 | 9,515 | 731,064 | `VENDAS` in liters |
| Vendas anuais de querosene iluminante por municipio | municipality-product-year | 1990-2024 | 15,133 | 1,148,376 | `VENDAS` in liters |

Measured total: 961,753 source rows and 62,920,814 bytes, about 60.0 MiB of
CSV.

Live import on 2026-07-01 wrote 1,104,043 normalized facts because GLP
municipality rows with `P13` and `OUTROS` are split into separate auditable
facts. The managed store contained 15 raw snapshots, 409 Parquet partitions,
754 rows in `fuel_distribution_product_year_mart`, and a state/month mart for
bounded trend reads.

## Source URLs

Monthly/state-level sources:

- `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vendas-derivados-petroleo-e-etanol/vendas-combustiveis-m3-1990-2025.csv`
- `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vcs/vendas-combustiveis-segmento-m3-2012-2025.csv`
- `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vct/vendas-glp-tipo-vasilhame-m3-2007-2025.csv`
- `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vct/vendas-oleo-diesel-tipo-m3-2013-2025.csv`
- `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vendas-por-produtor/vendas-oleo-diesel-produtores-m3-2025-2026.csv`
- `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vendas-de-biodiesel/vendas-biodiesel-b100-m3.csv`

Annual/municipality sources:

- `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vaehdpm/asfalto/vendas-anuais-de-asfalto-por-municipio.csv`
- `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vaehdpm/etanol-hidratado/vendas-anuais-de-etanol-hidratado-por-municipio.csv`
- `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vaehdpm/gasolina-c/vendas-anuais-de-gasolina-c-por-municipio.csv`
- `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vaehdpm/gasolina-de-aviacao/vendas-anuais-de-gasolina-de-aviacao-por-municipio.csv`
- `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vaehdpm/glp/vendas-anuais-de-glp-por-municipio.csv`
- `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vaehdpm/oleo-combustivel/vendas-anuais-de-oleo-combustivel-por-municipio.csv`
- `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vaehdpm/oleo-diesel/vendas-anuais-de-oleo-diesel-por-municipio.csv`
- `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vaehdpm/querosene-de-aviacao/vendas-anuais-de-querosene-de-aviacao-por-municipio.csv`
- `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vaehdpm/querosene-iluminante/vendas-anuais-de-querosene-iluminante-por-municipio.csv`

## Storage Decision

The measured ANP sales corpus is modest, but it should still follow the managed
storage model because it is sector detail, source-updated, and likely to expand
as more oil, gas, biofuel, price, logistics, or company-specific sources are
added.

Default pilot shape:

- keep official CSV files as raw snapshots under the user data root;
- parse source-specific columns into normalized typed facts;
- store detailed facts in cold Parquet partitioned by source dataset and year;
- store import catalog, source hashes, manifests, parser version, and mart
  build metadata in SQLite;
- publish only compact SQLite marts for default app reads.

Do not write the full detail corpus directly into `cvm_financials.db`,
`energy_kpis.db`, or `news.db`.

## Initial Fact Families

Implemented first pass:

- `fuel_sales_state_month_fact`: state/product/month observations from the
  monthly ANP sources.
- `fuel_sales_municipality_year_fact`: municipality/product/year observations
  from annual ANP files.
- `fuel_distribution_product_year_mart`: national yearly summary by source
  dataset, product, year, and official unit.
- `fuel_distribution_state_month_mart`: state/product/month summary from
  monthly ANP sources for bounded trend charts.

Not yet implemented:

- UI reads for sector/company screens.

The default UI should start from national, region, and state summaries. It
should load municipality-level detail only after the user filters to a product,
state, and year range.

## Audit Fields

Each parsed row must preserve:

- source dataset id and official URL;
- downloaded timestamp;
- source file hash;
- import batch id;
- parser version;
- source row number or source row hash;
- original period fields;
- normalized period fields;
- region, state, municipality, IBGE code when present;
- product, segment, vessel, origin/destination region when present;
- unit and scale.

## How To Refresh

Run:

```powershell
python scripts/data/import_fuel_distribution_sources.py
```

The command prefers `%USERPROFILE%\Documents\CVMAnalytics` when the installed
Energy KPI database exists. It downloads official ANP CSV files to a temporary
folder, copies the immutable raw snapshots into the managed store, writes
partitioned Parquet detail, updates `managed_dataset_catalog`, and rebuilds the
compact product-year and state-month marts.

## Read Contracts

The Python read service and desktop bridge expose:

- `get_fuel_distribution_product_year_summary`: reads
  `fuel_distribution_product_year_mart` for default overview summaries.
- `get_fuel_distribution_state_month_series`: reads
  `fuel_distribution_state_month_mart` for bounded state/product/month trends.
- `get_fuel_distribution_detail`: reads cold Parquet detail only after callers
  provide a source dataset, product, and year.

Default app screens should use the SQLite marts first. Detail reads stay
filtered and bounded so the UI does not scan the full managed Parquet store.

## Open Questions Before UI Work

- Whether to include all annual municipality files in v1 or start with gasoline
  C, diesel, ethanol, and GLP.
- Whether to normalize all volume facts to m3 while preserving official units,
  or keep official units only and convert in marts.
- Whether oil and gas company coverage needs company-specific price/logistics
  sources in a separate managed registration.
