# Foundational Development Characteristics

Use this document before starting large product features.

CVMAnalytics should not add analyst workflow layers before the data foundation
can support them. A page is useful only when the analyst can trust the data,
understand the source, and know what action comes next.

## Product Development Order

Build in this order unless there is a clear reason not to:

1. Source contract.
2. Local storage and refresh behavior.
3. Read model or bounded query path.
4. Source/readiness UI close to the data.
5. Analyst workflow page.
6. Export and audit trail.
7. Higher-level workflow such as Critical Factors, model, valuation, or thesis.

Do not start with the final workflow page if the source, database, or lineage
contract is weak.

## Foundation Gate

Before building a new feature, answer:

- What source powers it?
- Is the source official, external/unofficial, calculated, or manual?
- Where is the raw snapshot stored?
- What local table, mart, or cache serves the UI?
- What is the refresh behavior?
- What is the unit, period, currency, geography, and entity grain?
- What is missing, stale, partial, source-risky, or unavailable?
- What bridge/API method proves the data exists?
- What UI state shows loading, empty, error, partial, stale, and unavailable?
- What export or audit artifact must preserve the same caveats?

If these answers are not available, the next step is a source/readiness task, not
a new analyst workflow.

## Source-First Rules

- Preserve raw downloads and source snapshots.
- Keep local reads usable offline.
- Use bounded marts or cached read models for large datasets.
- Never coerce missing data to zero.
- Never silently fallback from official data to external data.
- Label source class and timestamp near the number when the data supports it.
- Treat source-risky connectors as partial, not failed, when useful local data
  is still available.
- Keep user-facing errors explicit and recoverable.

## Page Ownership Rules

| Data/workflow | Correct home |
| --- | --- |
| Macro, sector, system, market, benchmark indicators | Indicator Library |
| Company financial and operational metrics | Company Workspace |
| Plant, parcel, distributor, asset, unit economics | Specialist Energy/Asset workspace |
| Source health, refresh status, storage, diagnostics | Settings / Data Health |
| Mapping from official statements to Excel output | Excel Mapping |
| Assumptions, scenarios, forecast outputs | Model / Forecast Workspace |
| Company-specific factors linked to thesis and review | Critical Factors, after source readiness |

Do not place company-specific or asset-specific metrics inside the default
Indicator Library just because they are indicators.

## Minimalism Rule

Minimalism means fewer redundant surfaces, not less evidence.

Do not add a summary panel unless it adds at least one of:

- a decision;
- an action;
- source or method detail not already visible nearby;
- a clear exception or warning.

Empty placeholders for future workflows are product noise. Hide future modules
until the underlying source, bridge, storage, and behavior exist.

## Next-Feature Readiness Levels

Use these labels in planning docs:

| Level | Meaning | Build action |
| --- | --- | --- |
| Source-ready | Source, snapshot, local storage, refresh, read path, metadata, and caveats exist. | Build or improve workflow UI. |
| Partial | Some source/read path exists, but coverage, source risk, lineage, or grain is incomplete. | Improve source/readiness before workflow expansion. |
| Prepared | Docs or code scaffolding exists, but no user-reliable data path. | Do not expose as implemented. |
| Missing | No usable source contract or read path. | Define source contract first. |
| Manual-only | Analyst input can exist, but it is not data-backed. | Label as manual and do not create automated status. |

## Application To Critical Factors

Critical Factors should wait until enough source-ready or clearly partial drivers
exist for a sector/company. Otherwise the feature becomes a manual checklist or a
fake alert layer.

The correct next step before Critical Factors is:

```text
Sector driver map
-> source/readiness audit
-> missing source priorities
-> page/workspace ownership
-> only then Critical Factors
```

