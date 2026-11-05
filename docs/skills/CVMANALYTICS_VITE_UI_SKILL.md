---
name: cvmanalytics-vite-ui
description: Integration and acceptance contract for the React/Vite desktop UI.
---

# Vite UI Contract

Use this contract when changing or reviewing `apps/desktop-web`. Read the
relevant workspace code before editing. This file owns UI integration and
acceptance; it does not duplicate the project workflow or design system.

## Owners and evidence

| Question | Source of truth |
|---|---|
| Workflow, language, validation and final report | [AGENTS.md](../../AGENTS.md) |
| Product principles and workspace ownership | [PRODUCT.md](../PRODUCT.md), [PRODUCT_DIRECTION.md](../PRODUCT_DIRECTION.md) |
| Visual and interaction rules | [DESIGN.md](../DESIGN.md) |
| Implemented tokens and installed libraries | `apps/desktop-web/src/index.css`, `apps/desktop-web/package.json` |
| Runtime and launch commands | [architecture.md](../architecture.md), [development.md](../development.md) |

## Integration

```text
React route/component -> lib/api/<domain>.ts -> lib/bridge/adapter.ts
  -> window.pywebview.api -> desktop/bridge_api/<domain>.py -> Python services
```

- Keep bridge calls inside typed facades; components must not access the global
  bridge, SQLite or local filesystem paths directly.
- Preserve the bridge contract in `lib/bridge/types.ts` and the domain type files.
  Inspect the Python consumer when changing a payload.
- Preserve financial meaning, units, period and consolidation labels. Missing
  values remain missing; the frontend must not manufacture fallback observations.
- Use existing components from `src/components`; verify exports before reuse.
  Examples include `PageHeader`, `StateBanner` and `EntityHeader`. A component
  named in old migration notes is not evidence that it exists.
- Inspect package.json before proposing a dependency. `@base-ui/react` is not
  installed; using existing components does not require adding it.
- The packaged UI is Vite-only. Do not restore Next.js, bundled Node or a legacy
  web server. Route definitions live in `src/App.tsx`.

## Runtime states

| Mode | Required behavior |
|---|---|
| Desktop | Use the real Python bridge and show loading/error/data states. |
| Browser preview | Keep navigation usable and explain that the bridge is unavailable. Do not silently load mocks or claim access to local data. |
| Explicit mock preview | Fixtures require a dev build and `VITE_MOCK_BRIDGE=1`; use `npm --prefix apps/desktop-web run dev:mock`. Label fixtures as mock data. |

On a bridge failure, keep navigation available and show the error near the
failed operation with a useful retry or Settings -> Diagnostics path. Technical
tracebacks belong in diagnostics, not the main financial view. Do not introduce
external telemetry into the desktop UI.

Every data region must represent loading, empty, error, partial, stale and
loaded states as applicable. Empty data should offer a relevant next action;
stale or partial observations retain their source and timestamp. Never hide
source failures or replace missing numbers with zero.

## Review and acceptance

- Trace route -> component -> facade -> bridge -> service before changing behavior.
- Preserve active selections, query keys, exports, local persistence and errors
  during refactors; do not combine component extraction with a redesign.
- Check keyboard focus, explicit close paths, laptop-width tables, responsive
  panels and chart labels/gaps against DESIGN.md.
- Run the relevant checks from AGENTS.md and the commands in development.md.
  Browser mocks validate UI states, not real data behavior. Use the real desktop
  when feasible; release claims require packaged validation.
- Report only the scope, changes, validation and remaining limits required by
  AGENTS.md. There is no separate phase-report template for UI work.
