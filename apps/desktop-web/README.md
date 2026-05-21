# apps/desktop-web — Phase 1 parallel Vite SPA shell

## Status

**Proof-of-concept.** This package exists in parallel to `apps/web/` (Next.js). It does **not** replace the production UI. The released desktop executable still ships the Next.js standalone server.

## Goal

Prove that a static Vite + React + TypeScript build can drive the existing Python bridge (`desktop/bridge.py::CVMBridge`) without an embedded Node runtime. Once the prototype reaches parity it will replace `apps/web/` and remove the bundled `node.exe` (Phase 2 + Phase 3 in `docs/migration/`).

## What is here

```
apps/desktop-web/
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
├── public/
└── src/
    ├── App.tsx
    ├── main.tsx
    ├── index.css
    ├── components/
    │   └── HealthCard.tsx
    └── lib/
        ├── bridge/
        │   ├── adapter.ts     # single chokepoint for window.pywebview.api
        │   └── types.ts       # typed mirror of Python bridge methods
        └── api/
            └── health.ts      # facade consumed by components
```

## Bridge pattern

Components MUST NOT touch `window.pywebview.api` directly. They go through:

```
UI component
  -> lib/api/<facade>.ts     (one file per domain area)
  -> lib/bridge/adapter.ts   (callBridge + whenBridgeReady)
  -> window.pywebview.api    (injected by pywebview at runtime)
  -> Python bridge (desktop/bridge.py)
  -> Python service/core (src/*)
```

`callBridge<K>(method, params)` is the only typed entry point. Adding a new bridge method is a two-step change: add the signature to `BridgeApi` in `lib/bridge/types.ts`, then add a facade under `lib/api/`.

## Dev — browser

```bash
cd apps/desktop-web
npm install
npm run dev
```

Open `http://127.0.0.1:5173/`. The `HealthCard` will show a yellow "Browser-mode preview" banner because `window.pywebview.api` is not injected by a real browser. This is the expected dev-without-Python flow.

## Dev — inside pywebview

```bash
cd <repo root>
python -m desktop.app --dev
```

This currently still launches the Next.js dev server. Phase 2 will add a pywebview launch mode that points at the Vite dev server or the built static assets, at which point `HealthCard` will resolve in `desktop` mode and show real Python bridge data.

## Build

```bash
cd apps/desktop-web
npm run build
```

Output is a static SPA at `apps/desktop-web/dist/`. Phase 2 will wire this dir into `desktop/app.spec` and `desktop/app.py` so the packaged exe loads it directly (no Node, no Next standalone server).

## What this does NOT do yet

- Does not run inside the packaged exe.
- Does not replace any Next.js route.
- Does not implement routing — single screen only.
- Does not implement state caching (TanStack Query comes in Phase 1.5).
- Does not call FastAPI. Bridge-only.
