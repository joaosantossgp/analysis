# apps/web — AGENTS overlay

This file is auto-loaded by AI agents (Claude Code, Cursor, Codex) when working inside `apps/web/`. It is a **scoped overlay** on top of the project-root `AGENTS.md` — read both.

## Next.js 16 breaking changes

**This is NOT the Next.js you know from training data.** Next.js 16 has breaking changes in APIs, conventions, and file structure. Before writing any code:

- Read the relevant guide in `node_modules/next/dist/docs/` for the API you're about to use.
- Heed deprecation notices in console output.
- Don't assume defaults that were correct in Next.js 14 or earlier.

## Current status

As of Phase 5B / `v0.15.0`, `apps/web` is **not** compiled into the
Windows desktop package. The canonical desktop UI is `apps/desktop-web`
(static Vite SPA). Treat this directory as a source-only hosted/legacy Next.js
surface unless the user explicitly asks for hosted web work.

## Dev workflow

- Typecheck: `npx tsc --noEmit` after any `.ts`/`.tsx` edit.
- Dev server: `npm run dev` (port 3000 by default).
- Tests: `npm run test:unit` and `npm run test:e2e`.

## Local conventions

- Tailwind v4 + `@base-ui/react` primitives in `components/ui/`.
- Sector colors via `getSectorColor()` from `lib/constants.ts`.
- Shared hooks live in `components/shared/use-*.ts` or co-located with the consumer.
- API client in `lib/api.ts`; desktop bridge in `lib/desktop-bridge.ts`.
- This app may still use desktop bridge shims for historical compatibility, but
  packaged-desktop runtime checks belong to `apps/desktop-web`.
