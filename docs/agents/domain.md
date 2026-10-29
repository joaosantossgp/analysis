# Domain Docs

How the engineering skills should consume this repo's domain documentation when
exploring the codebase. This repo is single-context but predates the default
layout, so the locations below differ from the skill defaults.

## Before exploring, read these

- **`GLOSSARY.md`** at the repo root, if it exists. There is none yet; create it
  there when `/domain-modeling` resolves terms.
- **`docs/CONTEXT.md`**: financial pipeline domain rules (statements, periods,
  `LINE_ID_BASE`, QA, coverage, freshness). It is not a glossary; do not rename
  it to `GLOSSARY.md`.
- **`docs/data-sources.md`**: source classes, storage rules, and the
  interpretation distinctions every number must preserve.
- **`docs/PRODUCT_DIRECTION.md`**: analyst workflow and workspace ownership.
- **`docs/decisions/`**: the ADRs. This repo uses `docs/decisions/`, not
  `docs/adr/`. Read ADRs that touch the area you are about to work in, and
  check each one's status (some are historical or withdrawn).

If a file does not exist, proceed silently.

## Writing new decisions

Write new ADRs to `docs/decisions/NNNN-short-slug.md` with the next free number,
a `Status:` line, and context/decision/consequences. Add the ADR to the index in
`docs/decisions/README.md`.

## Use the project's vocabulary

When your output names a domain concept (issue title, refactor proposal,
hypothesis, test name), use the term as these docs define it. CVM/B3 terms,
statement names (DFP, ITR, BPA, BPP, DRE, DFC), and line items stay as
published.

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than
silently overriding:

> _Contradicts ADR-0007 (local analytical storage), but worth reopening because..._
