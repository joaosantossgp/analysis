# Worktree Cleanup, Dependency Security, and Main Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the current Company Workspace work in reviewable branches, clear the working tree, update `main` to `origin/main`, and remove the five npm audit vulnerabilities without changing product behavior.

**Architecture:** Treat the local Company Workspace edits and dependency security work as separate deliverables. First capture the product work on a feature branch, then fast-forward `main`, rebase the feature branch, and create a second branch from the updated `main` for the lockfile-only security update. Do not merge either branch as part of this plan.

**Tech Stack:** Git, GitHub remote `origin`, npm lockfile v3, Vite 6, React Router 7, Vitest, TypeScript.

## Global Constraints

- Preserve all intended Company Workspace source, test, and documentation changes; do not reset, checkout, or discard them.
- Do not commit `.codex/audits/company-overview/*.png`; retain those screenshots outside the repository or under ignored `output/`.
- Do not restore the removed `.codex/skills/next-step` skill.
- Keep `apps/desktop-web/package.json` unchanged for the security update; its existing ranges accept the remediated versions.
- Do not modify legacy Next.js paths. The active frontend is `apps/desktop-web`.
- Run `npm --prefix apps/desktop-web run typecheck` after any TypeScript or TSX edit.
- Use `git pull --ff-only` on `main`; never force-push, reset, or merge remote history locally.

---

## Current-State Record

At planning time, `main` is 25 commits behind `origin/main` and has zero local commits ahead. The local product changes affect the Company directory, Company Overview, command bar, entity header, tests, and three product/design documents. The audit reports five vulnerable package records:

| Record | Installed version | Remediated version from `npm audit fix --dry-run` |
| --- | --- | --- |
| `vite` | `6.4.2` | `6.4.3` |
| `react-router-dom` | `7.15.1` | `7.18.2` |
| `react-router` | `7.15.1` | `7.18.2` |
| `postcss` | `8.5.15` | `8.5.24` |
| `@babel/core` | `7.29.0` | `7.29.7` |

`npm audit fix --dry-run` also updates 21 non-vulnerable transitive packages in the same lockfile resolution. This is expected and must be reviewed as one generated `package-lock.json` change.

## Local Change Disposition

| Files | Decision | Rationale |
| --- | --- | --- |
| `apps/desktop-web/src/components/CompaniesTable.tsx`, `apps/desktop-web/src/components/CompaniesTable.test.ts` | Preserve in Company Workspace branch | Makes the directory a row-selectable issuer index and removes the duplicate coverage editor. Coverage actions remain available in `CoveragePage.tsx` and `CompanyCoveragePage.tsx`. |
| `apps/desktop-web/src/components/CompanyCommandBar.tsx`, `apps/desktop-web/src/components/CompanyCommandBar.test.ts` | Preserve in Company Workspace branch | Adds links to implemented Statements and Excel Mapping workspaces and makes command labels explicit. |
| `apps/desktop-web/src/components/EntityHeader.tsx`, `apps/desktop-web/src/components/EntityHeader.test.ts`, `apps/desktop-web/src/components/data/IdentifierBadge.tsx` | Preserve in Company Workspace branch | Standardizes visible classifications on GICS Sector and Industry Group while retaining CVM-sector context in a tooltip. |
| `apps/desktop-web/src/routes/CompanyDetailPage.tsx`, `apps/desktop-web/src/routes/__tests__/CompanyFinancialReadiness.test.ts` | Preserve after state validation | Removes the redundant readiness panel but retains command-bar refresh/export actions. Verify ready, partial, failed, and no-local-data states before committing. |
| `docs/DESIGN.md`, `docs/PRODUCT_DIRECTION.md`, `docs/company-workspace-overview-ia-plan.md` | Preserve only after wording decision | The new text prefers contextual detail without navigation, while the directory now navigates to the Company Workspace. Align the wording with the chosen interaction before committing. |
| `.codex/audits/company-overview/*.png` | Preserve outside Git | Local visual evidence, not a source artifact. Move to ignored `output/` or an external archive before final cleanliness checks. |
| `.codex/skills/next-step/**` | Remove | The user explicitly requested deletion. The folder has already been removed and must remain absent. |

### Task 1: Capture the Company Workspace Work Safely

**Files:**
- Create: `docs/superpowers/plans/2026-07-28-worktree-security-and-main-sync.md`
- Modify: `apps/desktop-web/src/components/CompaniesTable.tsx`
- Modify: `apps/desktop-web/src/components/CompanyCommandBar.tsx`
- Modify: `apps/desktop-web/src/components/EntityHeader.tsx`
- Modify: `apps/desktop-web/src/components/data/IdentifierBadge.tsx`
- Modify: `apps/desktop-web/src/routes/CompanyDetailPage.tsx`
- Modify: `docs/DESIGN.md`
- Modify: `docs/PRODUCT_DIRECTION.md`
- Modify: `docs/company-workspace-overview-ia-plan.md`
- Test: `apps/desktop-web/src/components/CompaniesTable.test.ts`
- Test: `apps/desktop-web/src/components/CompanyCommandBar.test.ts`
- Test: `apps/desktop-web/src/components/EntityHeader.test.ts`
- Test: `apps/desktop-web/src/routes/__tests__/CompanyFinancialReadiness.test.ts`

**Consumes:** Current dirty working tree on `main` and the existing Company Workspace routes.

**Produces:** A clean `codex/company-workspace-refinement` branch containing only intended source, test, and aligned documentation changes.

- [ ] **Step 1: Create the preservation branch without changing the dirty files**

Run:

```powershell
git switch -c codex/company-workspace-refinement
git status --short --branch
```

Expected: branch is `codex/company-workspace-refinement`; all existing Company Workspace edits are still present.

- [ ] **Step 2: Decide and align the directory interaction contract**

Use this explicit decision: rows navigate to `/empresas/:cdCvm` because the Company Workspace is the intended deep-work surface. Update the three documentation files so they say that contextual detail is preferred where it preserves a current analytical task, while navigation is appropriate when opening the issuer workspace from the directory.

Run:

```powershell
rg -n "preserve.*context|navigation jump|first interaction|directory" docs/DESIGN.md docs/PRODUCT_DIRECTION.md docs/company-workspace-overview-ia-plan.md
```

Expected: no wording claims that every directory selection must remain in place.

- [ ] **Step 3: Run focused Company Workspace tests**

Run:

```powershell
npm --prefix apps/desktop-web run test -- CompaniesTable CompanyCommandBar EntityHeader CompanyFinancialReadiness
```

Expected: all four test files pass.

- [ ] **Step 4: Verify browser-visible behavior with mock data**

Run the mock runtime and verify:

```text
1. Open the Companies directory.
2. Activate one company row by mouse and by Enter.
3. Confirm navigation to /empresas/:cdCvm.
4. On the Overview, confirm Statements and Excel mapping links work.
5. Confirm financial indicators, market history, source methodology, and company identity render.
6. Exercise ready, partial, failed, and no-local-data fixtures or mocked bridge responses.
```

Expected: no console errors; every state remains visibly truthful; no removed readiness field is the sole location of refresh failure information.

- [ ] **Step 5: Run the required frontend validation**

Run:

```powershell
npm --prefix apps/desktop-web run test
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
```

Expected: all commands exit with status `0`.

- [ ] **Step 6: Stage only the Company Workspace source, tests, and aligned docs**

Run:

```powershell
git add apps/desktop-web/src/components/CompaniesTable.tsx apps/desktop-web/src/components/CompaniesTable.test.ts apps/desktop-web/src/components/CompanyCommandBar.tsx apps/desktop-web/src/components/CompanyCommandBar.test.ts apps/desktop-web/src/components/EntityHeader.tsx apps/desktop-web/src/components/EntityHeader.test.ts apps/desktop-web/src/components/data/IdentifierBadge.tsx apps/desktop-web/src/routes/CompanyDetailPage.tsx apps/desktop-web/src/routes/__tests__/CompanyFinancialReadiness.test.ts docs/DESIGN.md docs/PRODUCT_DIRECTION.md docs/company-workspace-overview-ia-plan.md docs/superpowers/plans/2026-07-28-worktree-security-and-main-sync.md
git diff --cached --check
git diff --cached --stat
```

Expected: no whitespace errors and no `.codex` files staged.

- [ ] **Step 7: Commit the preserved product work**

Run:

```powershell
git commit -m "feat(company): refine directory and overview workspace"
git status --short
```

Expected: the intended product files are committed; only local audit screenshots, if not yet moved, remain untracked.

### Task 2: Remove Local-Only Audit Artifacts and Update Main

**Files:**
- Move: `.codex/audits/company-overview/*.png` to ignored `output/company-overview-audit/` or an external archive
- Modify: no tracked files

**Consumes:** Committed Company Workspace branch from Task 1.

**Produces:** A clean worktree and `main` fast-forwarded to `origin/main`.

- [ ] **Step 1: Move audit screenshots out of the Git worktree state**

Run:

```powershell
New-Item -ItemType Directory -Force output/company-overview-audit | Out-Null
Move-Item -LiteralPath .codex/audits/company-overview/*.png -Destination output/company-overview-audit/
Remove-Item -LiteralPath .codex/audits/company-overview -Force
Remove-Item -LiteralPath .codex/audits -Force
Remove-Item -LiteralPath .codex -Force
git status --short
```

Expected: no `.codex/` entries in `git status`; screenshots remain locally available below ignored `output/`.

- [ ] **Step 2: Confirm the feature branch is clean**

Run:

```powershell
git status --porcelain
```

Expected: no output.

- [ ] **Step 3: Fast-forward main**

Run:

```powershell
git switch main
git fetch origin
git pull --ff-only origin main
git status --short --branch
git rev-list --left-right --count HEAD...origin/main
```

Expected: `main...origin/main` with no ahead/behind marker and divergence `0 0`.

- [ ] **Step 4: Rebase the Company Workspace branch on updated main**

Run:

```powershell
git switch codex/company-workspace-refinement
git rebase main
git status --short --branch
```

Expected: rebase completes. If conflicts occur, resolve only affected Company Workspace files, then repeat Task 1 Steps 3 through 5.

### Task 3: Produce the Lockfile-Only Security Update

**Files:**
- Modify: `apps/desktop-web/package-lock.json`
- Preserve: `apps/desktop-web/package.json`

**Consumes:** Updated `main` from Task 2.

**Produces:** A clean, reviewable `codex/dependency-security-2026-07` branch with zero npm audit vulnerabilities.

- [ ] **Step 1: Create a security branch from updated main**

Run:

```powershell
git switch main
git switch -c codex/dependency-security-2026-07
git status --short --branch
```

Expected: a clean new branch based on the up-to-date `main`.

- [ ] **Step 2: Apply only non-breaking audit resolutions**

Run:

```powershell
npm --prefix apps/desktop-web audit fix --package-lock-only
git diff -- apps/desktop-web/package.json
git diff --stat apps/desktop-web/package-lock.json
```

Expected: `package.json` has no diff; only `package-lock.json` changes.

- [ ] **Step 3: Verify each remediated package and the audit result**

Run:

```powershell
npm --prefix apps/desktop-web ci
npm --prefix apps/desktop-web ls vite react-router-dom react-router postcss @babel/core --all --depth=3
npm --prefix apps/desktop-web audit
```

Expected: Vite is at least `6.4.3`; React Router packages are at least `7.18.2`; PostCSS is at least `8.5.24`; Babel Core is at least `7.29.7`; `npm audit` reports `found 0 vulnerabilities`.

- [ ] **Step 4: Run full frontend compatibility validation**

Run:

```powershell
npm --prefix apps/desktop-web run test
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
```

Expected: all commands exit with status `0`.

- [ ] **Step 5: Stage and commit the lockfile-only remediation**

Run:

```powershell
git add apps/desktop-web/package-lock.json
git diff --cached --check
git diff --cached --name-only
git commit -m "chore(web): resolve npm audit vulnerabilities"
git status --short
```

Expected: only `apps/desktop-web/package-lock.json` is committed and the branch is clean.

### Task 4: Final Branch and Main Verification

**Files:**
- Modify: no files

**Consumes:** The two clean branches from Tasks 2 and 3.

**Produces:** Evidence that `main` is current and both pending changes are isolated for review.

- [ ] **Step 1: Verify main is still current**

Run:

```powershell
git switch main
git fetch origin
git status --short --branch
git rev-list --left-right --count HEAD...origin/main
```

Expected: clean worktree and divergence `0 0`.

- [ ] **Step 2: Review the Company Workspace branch against main**

Run:

```powershell
git diff --check main...codex/company-workspace-refinement
git log --oneline main..codex/company-workspace-refinement
```

Expected: no whitespace errors and only the intended Company Workspace commit(s).

- [ ] **Step 3: Review the security branch against main**

Run:

```powershell
git diff --check main...codex/dependency-security-2026-07
git diff --name-only main...codex/dependency-security-2026-07
git log --oneline main..codex/dependency-security-2026-07
```

Expected: no whitespace errors; only `apps/desktop-web/package-lock.json` differs; one security commit is present.

## Plan Self-Review

- Coverage: preserves current product work, removes local-only skill/audit state, fast-forwards `main`, separates dependency remediation, and specifies validation for the five audit records.
- Scope: the Company Workspace branch and security branch have independent write-sets and can be reviewed independently.
- Risk: the only product decision requiring confirmation is whether Company directory selection should navigate directly or open contextual detail. This plan selects direct navigation and requires the docs to state that exception accurately.
- No merge, push, pull request, reset, or deletion of intended source changes is authorized by this plan.
