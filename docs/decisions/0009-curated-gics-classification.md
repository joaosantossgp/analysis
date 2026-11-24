# 0009: Curated GICS classification

Status: Accepted (2026-11-24)

## Context

The app showed different sectors for the same company depending on the screen:
sector queries read `setor_analitico`/`setor_cvm`, the Companies table read
`gics_*` columns, and the indicator panel read `setor_cvm`. The bundled GICS
mapping was almost entirely derived from CVM sector labels (656 of 670 rows),
stored as names without codes and without provenance, which contradicted the
rule "never infer GICS from CVM/B3/ticker/name". Official GICS assignments
require an MSCI/S&P license; no public crosswalk exists for Brazilian issuers.

## Decision

- GICS is **curated by CVMAnalytics**, at sub-industry level, for every company
  with an active CVM registration. Each assignment records basis, confidence,
  rationale, evidence URL, review status and GICS version, and is never
  presented as an official MSCI/S&P classification.
- Curation happens at development time (two independent model passes with web
  search, a coherence check against CVM sectors, and owner review). Nothing
  AI-based runs in the product.
- The curated dataset ships with each release and is materialized into the
  existing `companies.gics_*` columns on startup, so every read path shows the
  same value. Companies without a curated value are explicitly `pending`.
- The analyst can override locally (#521); local edits are never overwritten by
  updates.
- This replaces the previous "never infer GICS" rule in `AGENTS.md` and
  `docs/reference/gics-import.md`.

## Consequences

- One canonical sector per company across screens; derived levels are
  consistent by construction.
- The CVM-derived startup backfill and bundled mapping are retired (#525).
- Curated values can be wrong; low/medium confidence and pass disagreements are
  recorded so they can be found and corrected.
- A future GICS structure change needs a new `gics_version` and a re-curation of
  affected sub-industries.
