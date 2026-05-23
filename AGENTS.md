# AGENTS.md

Canonical operating rules for AI agents in this project. English-only. ~120 lines.

## 1. How to read this file

- This is the **default** contract. Read once per session.
- For a full map of every folder, workflow, and doc status, see `docs/reference/repository-map.md`.
- For long-running autonomous PRs, also read `docs/governance/autonomous-mode.md`.
- Before touching `src/` or `apps/api/`, also read `docs/CONTEXT.md`.
- Before touching `apps/web/`, the per-directory `apps/web/AGENTS.md` is auto-loaded.
- Before implementing or reviewing any Vite UI screen in `apps/desktop-web`, read and follow: [docs/skills/CVMANALYTICS_VITE_UI_SKILL.md](docs/skills/CVMANALYTICS_VITE_UI_SKILL.md).
- Active reference docs live in `docs/reference/`. ADRs live in `docs/decisions/`. Migration history lives in `docs/migration/` (all phases complete as of v0.17.0).
- `archive/` (at root) is historical — governance snapshots and old experiments. Do not treat as current contract.

## 2. Principles

1. **Inspect before editing.** Read the file you're changing and at least one of its callers. Never fabricate project state.
2. **Prefer small, reviewable changes.** One concern per edit. If a task spans multiple concerns, finish one cleanly, then start the next.
3. **Preserve architecture unless asked to change it.** If you must change it, say so explicitly and propose the alternative before doing it.
4. **Ask only questions that change scope, correctness, or quality.** Don't ask permission on reversible decisions inside a granted scope.
5. **Validate what you can validate.** Run typecheck/lint/tests when the change is testable. Run the dev server when the change is observable. If you cannot validate, say so plainly — don't claim success.
6. **Surface assumptions and risks at the end of the work.** In 1–3 lines: what could go wrong, what wasn't verified, what to watch for.
7. **Don't speculate-engineer.** No memoization without a measured win, no abstraction for hypothetical second callers, no comments that re-narrate the code.
8. **Match the language of the surrounding code.** Some files are Portuguese, some English. Use whichever the file you're editing already uses.
9. **Be honest about audit/finding quality.** If you delegate analysis to a subagent and the findings don't hold up on inspection, say so. Don't relay confidence you don't have.
10. **Data/financial/modeling work:** prioritize auditability and correctness over speed. Preserve column conventions; honor `docs/CONTEXT.md`.
11. **UI/design work:** keep output professional and consistent with the existing design system. Preserve creative latitude — propose visual options when not constrained.
12. **Autonomous (long-running) work:** route through `docs/governance/autonomous-mode.md`. Interactive sessions use this file only.

## Token and Context Efficiency Protocol

Use context-efficient tools before reading large files.

### Serena MCP

When Serena is available, use it first for code navigation, symbol search, reference lookup, and refactoring analysis.

Prefer Serena for:

- finding symbols, components, functions, classes, and references
- understanding cross-file dependencies
- inspecting file outlines before reading full files
- planning refactors across multiple files
- checking where a function/component is used before editing it

Avoid reading full files unless:

- the exact implementation is required
- Serena's symbolic overview is insufficient
- debugging requires full local context

At the beginning of a new session, activate the current project with Serena and read Serena's initial instructions if they are not already loaded.

### Repomix

Use Repomix outputs only for broad repository understanding, onboarding, architecture review, or high-level planning.
Do not rely on Repomix compressed output for precise implementation changes. For exact edits, inspect the real source files or use Serena.

### Cost Discipline

Before large changes, inspect the relevant subsystem first.
Avoid broad grep/read loops across the whole repository.
When the task changes substantially, start a fresh session or compact/clear the context.
Prefer targeted plans, small diffs, and focused validation commands.

## 3. Plan-mode rule (risk-based, not ceremony-based)

- **Low risk** (typo, copy fix, isolated function, formatter swap, single-component prop tweak): inspect, act, one-line summary.
- **Medium risk** (multi-file refactor, new component, non-trivial logic change, new hook): state the plan in 2–4 lines, then act.
- **High risk** (architecture, data model, DB schema, financial calculations, auth/security, destructive ops, repo-wide changes, dependency changes): plan in full and **wait for approval**.
- **"Only plan" / "plan only" / "draft"**: plan; do not edit files.
- **"Do next" / "go" / "proceed"**: proceed with the agreed step without re-asking, unless new risk appears.

## 4. Validation expectations

- Desktop UI TypeScript: `npm --prefix apps/desktop-web run typecheck` after any
  desktop UI TS/TSX edit.
- Source-only hosted web TypeScript: `npm --prefix apps/web run typecheck` after
  any `apps/web/` TS/TSX edit.
- Python: `pytest tests/` for desktop/core paths, `pytest apps/api/tests/` when
  intentionally editing the hosted API.
- UI-observable changes: start the dev server and verify when feasible (browser preview, screenshot, snapshot).
- If validation is skipped, say why explicitly in the wrap-up.

## 5. Task modes

Each task type has a minimal extra rule on top of the principles. Match the mode to the work; don't blend them.

### Bugfix

- Reproduce or read the error trace before proposing a fix.
- Fix the root cause, not the symptom.
- Add a regression test only if the bug came from a previously untested path.

### Feature

- Confirm scope before designing. If the request is ambiguous, ask one targeted question.
- Prefer additive changes over rewrites.
- Validate end-to-end before declaring done.

### Refactor

- **No behavior change.** State what's preserved and what's moving.
- Verify with typecheck + tests; do not add new features in the same pass.
- If a "refactor" requires a behavior change, stop and re-scope.

### UI / UX / design

- Honor the existing design system (Tailwind tokens, `@base-ui/react`, sector colors via `getSectorColor`, OKLCH palette).
- Verify visually in the dev server when the change is observable.
- Preserve creative latitude — propose 2–3 visual options when the brief is not constrained.

### Data / modeling / financial logic

- Read `docs/CONTEXT.md` first.
- Prioritize auditability and correctness over speed.
- Validate against known fixtures, not just type signatures.
- Never infer GICS classifications from CVM/B3/ticker/name (see `docs/reference/gics-import.md`).

### Docs / research

- No code edits in this mode.
- Output is documentation, findings, or recommendations.
- Cite file paths with line numbers when referencing code.

### Autonomous (opt-in only)

- Route through `docs/governance/autonomous-mode.md`.
- Default workflow does NOT use issue-first / worktrees / risk labels / draft PRs.

## 6. Source-of-truth pointers

- `README.md` — project overview
- `COMO_RODAR.md` — how to run locally (Portuguese, operational)
- `docs/CONTEXT.md` — domain rules for `src/` and `apps/api/`
- `docs/decisions/` — ADRs (durable architectural decisions)
- `docs/reference/` — active reference docs (sitemap, interface map, API contract, perf baseline, GICS import, product page prompts)
- `docs/governance/autonomous-mode.md` — opt-in heavy contract for autonomous PRs

## 7. What NOT to do

- Don't open PRs in draft because the change touches multiple files. Draft only when the work itself is incomplete.
- Don't use the GitHub CLI (`gh`) or `scripts/pr_complete.ps1` for routine merges. Standard `git push` + manual or auto-merge is sufficient.
- Don't insist on issue-first, worktrees, lanes, or risk labels for interactive sessions. These belong to autonomous mode only.
- Don't load stale planning docs as context — they were deleted. If you find references to `STUDENT_PACK_PLAN`, `WEBAPP_TRANSFORMATION_PLAN`, `V2_PHASE1_BACKEND`, etc., they no longer exist.
- Don't follow `CLAUDE.md`, `CONTRIBUTING.md`, or `docs/GOVERNANCE_QUICK_REFERENCE.md` — they were folded into this file and deleted.
- Don't assume Vercel/Railway hosting. The canonical product is the Windows `CVMAnalytics.exe` desktop app (`desktop/build_desktop.ps1`).

## 8. Canonical product

- **Shipped runtime:** `dist/CVMAnalytics/CVMAnalytics.exe` (built via `desktop/build_desktop.ps1`).
- **Architecture:** pywebview serves the static Vite SPA from `apps/desktop-web`
  / `_internal/desktop-web` and talks to Python through `desktop/bridge.py`.
- **Data root:** packaged users store runtime data under
  `%USERPROFILE%\Documents\CVMAnalytics`.
- **`apps/desktop-web`** is the only UI source compiled into the desktop bundle.
- **`apps/web`** is source-only hosted/legacy Next.js; it is not packaged.
- **`apps/api`** is source-only hosted/development FastAPI; it is not packaged.
- Validate product bugs against the packaged desktop app and the Documents data
  root, not remote URLs.
