# GICS Import

This project must not infer GICS classifications from CVM, B3, ticker, company
name, or custom sector labels. CVM/B3/native labels are useful metadata, but
they are not GICS. Treating them as GICS creates false sectors and misleading
counts.

GICS is populated only from an explicit mapping file approved by the project
owner.

## Expected File

Place the approved file at:

```text
data/import/gics_mapping.csv
```

Required CSV columns:

```csv
cd_cvm,gics_sector,gics_sub_industry,source,as_of_date
```

Optional diagnostic columns:

```csv
ticker,company_name,cnpj,notes
```

Rules:

- `cd_cvm` is the only key used for database updates.
- `gics_sector` must be one of the 11 official GICS sector labels used by the app.
- `gics_sub_industry` must be present and non-empty.
- `source` must identify the approved source.
- `as_of_date` must use `YYYY-MM-DD`.
- `ticker`, `company_name`, and `cnpj` are diagnostics only. They can help
  report possible matches or mismatches, but they do not authorize updates.

## Commands

Dry-run is the default. It validates the CSV, matches by `cd_cvm`, writes a
report, and does not update the database:

```powershell
python scripts/import_company_gics.py
```

Apply mode is explicit:

```powershell
python scripts/import_company_gics.py --apply
```

Sanity-check mode does not require the CSV. It checks the current schema,
company table size, current GICS counts, and writes the same report file:

```powershell
python scripts/import_company_gics.py --check
```

The report is written to:

```text
data/reports/gics_backfill_report.json
```

## Report Fields

The report includes:

- mappings read
- invalid rows
- duplicate `cd_cvm` rows
- matched companies
- unmatched mappings
- fallback-key diagnostics, without applying those matches
- companies that would be updated in dry-run
- companies updated in apply mode
- companies skipped and skip reasons
- companies still unclassified
- distinct GICS sectors after import
- distinct GICS sub-sectors after import
- source values found
- as-of dates found
- current physical `gics_*` field counts in the DB

In dry-run/apply import modes, `companies_still_unclassified` and the
"after import" sector lists are based on the approved CSV coverage, not on old
physical `gics_*` values already present in the database. This matters during
recovery because old non-null GICS fields may be untrusted. The report also
shows the current physical DB field counts separately for diagnostics.

In `--check` mode, no approved CSV is loaded, so the summary describes the
current physical DB fields only.

## Universe Check

GICS import updates only companies already present in `companies`. It does not
add companies and does not touch `financial_reports`.

Before applying a full mapping, confirm that `companies` represents the full CVM
active company universe. The importer reports when the active-universe cache is
larger than `companies`.

If the universe is incomplete, seed or reconcile `companies` first, then rerun:

```powershell
python scripts/seed_catalog.py --dry-run
python scripts/seed_catalog.py
python scripts/import_company_gics.py --check
```

## Safety Warning

Never use `setor_cvm`, `setor_analitico`, B3 sector labels, ticker names, or
normalized company names as GICS. They can be displayed as their own metadata
only when clearly labeled, but they must not be mixed into GICS sector or
sub-sector views.
