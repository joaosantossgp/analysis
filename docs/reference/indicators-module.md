# Indicators Module

Active reference for the desktop `Indicators` module at `apps/desktop-web/src/routes/CountryKpisPage.tsx`.

## Product Shape

- Route: `/country-kpis` remains the stable URL for backward compatibility.
- Top navigation label: `Indicators`.
- Top-level tabs:
  - `Macroeconomic`: country-level and system-level context.
  - `Sector & Company`: microeconomic sector snapshots and company-level KPI coverage.

## Macroeconomic Tab

The macro tab contains local-first operating context that is not tied to one company:

- `Country Energy`: existing country-level Energy Utilities KPIs from `energy_kpis.db`, including electricity matrix, demand, carbon intensity, and trade.
- `SIN Subsystems`: Brazilian subsystem KPIs from ONS/CCEE local snapshots. See `docs/reference/energy-utilities-sin-kpis.md`.

Reads are offline-only. Manual refresh actions are explicit and source-specific:

- Country energy refresh: `refresh_energy_kpis`.
- SIN refresh: `refresh_sin_kpis`.

## Sector & Company Tab

The micro tab reuses existing CVM local data through the bridge:

- Sector snapshots: `get_sectors` through `apps/desktop-web/src/lib/api/sectors.ts`.
- Company coverage: `get_companies` through `apps/desktop-web/src/lib/api/companies.ts`.

This tab is intentionally not a new data layer. It is the UI organization point for company and sector indicators already owned by the CVM read-service/KPI engine.

## Runtime Contract

React components must keep using the facade path:

```text
UI component
-> apps/desktop-web/src/lib/api/*
-> apps/desktop-web/src/lib/bridge/adapter.ts
-> window.pywebview.api
-> desktop/bridge.py
-> Python services / SQLite
```

Browser/mock mode must render useful fixture data without hitting Python. Desktop/dev mode uses the real bridge and local databases.

## Validation

After changing this module, run:

```powershell
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
python -m pytest tests/energy_kpi -q
```
