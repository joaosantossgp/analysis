# GICS Classification

Every company has one canonical industry classification: a GICS sub-industry
**curated by CVMAnalytics**. Sector, industry group and industry are derived
from the sub-industry code, so the levels never contradict each other. The
classification is never presented as an official MSCI/S&P assignment.
Decision record: [ADR 0009](../decisions/0009-curated-gics-classification.md).

## Sources and files

| File | Content |
|---|---|
| `data/reference/gics_structure.csv` | Current GICS hierarchy: codes and names for the 4 levels (11/25/74/163), structure effective March 2023, definitions as of February 2025, discontinued codes excluded. Long definitions are proprietary and are not committed. |
| `data/curation/gics_curated.csv` | One row per curated company: `cd_cvm`, `sub_industry_code` (or `unclassified_reason`), `basis`, `confidence`, `rationale`, `evidence_url`, `review_status`, `reviewer`, `review_date`, `proposed_by`, `gics_version`. `company_name` and `cnpj` are diagnostics only. |
| `data/curation/gics_full_review.csv`, `gics_*_report.json` | Curation evidence: both independent passes, review reasons, batch IDs and cost. |

Curation is a development-time process (`scripts/curation/`), not an app
feature. No AI runs inside CVMAnalytics. CVM and B3 sector labels may be used
as curation inputs and are shown as their own labelled metadata, but they are
never copied into GICS fields.

## Rules

- Classify by principal business activity (primarily revenue), following the
  GICS methodology. Diversified holdings without a dominant business use
  Multi-Sector Holdings (`40201030`).
- When the activity cannot be determined (shell, pre-operational, bankrupt
  estate), the row has no code and an `unclassified_reason`. Never guess.
- Every assignment records its basis, confidence, rationale, evidence and GICS
  version. `review_status=accepted_without_review` means the owner accepted the
  batch without checking it row by row.

## Runtime behavior

- On every startup (packaged and dev), the app validates the shipped curated
  dataset, loads it into `company_classification_curated`, and materializes it
  into `companies.gics_*`, `gics_sub_industry_code` and `classification_origin`.
- `classification_origin` is `user` (local edit), `curated`, `unclassified` (curated as not
  classifiable, with a reason) or `pending` (not curated yet). Pending and
  unclassified companies have empty GICS fields; screens show "Pending" or
  "Not classifiable", never a fallback label.
- An invalid dataset (unknown code, duplicate `cd_cvm`, missing reason) is
  rejected before any write; the previous classification stays and the error
  goes to `recovery.log`.
- Companies written later (refresh, catalog seed) pick up their curated
  classification immediately.
- The Companies sector filter adds "Pending classification" and
  "Not classifiable" options (slugs `pending-classification`,
  `not-classifiable`) whenever such companies exist.
- Companies whose CVM registration is cancelled keep their classification and
  data; the company header shows "Registration cancelled". Curation rounds only
  cover active registrations.
- The analyst can edit a company's sub-industry from the company header
  ("Edit classification"). The edit is stored in `company_classification_user`,
  wins over the curated value on every screen (`classification_origin=user`),
  and is never overwritten by app updates. If a later curated value differs from
  the one at edit time, the header shows a notice. "Revert to curated" deletes
  the local edit. Bridge methods: `get_gics_structure`,
  `set_company_classification`, `clear_company_classification`.

## Legacy importer

The CVM-derived GICS importer and its `data/import` mapping CSVs were removed
in #525.
