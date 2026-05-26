# Autonomous Mode

**Opt-in only.** This contract applies to long-running, semi-autonomous agent work where the human is not actively reviewing each edit — e.g., scheduled batch refactors, multi-PR cleanup runs, or any flow where an agent will produce a PR end-to-end without intermediate prompts. Routine interactive work uses `AGENTS.md` only.

The full default principles in `AGENTS.md` still apply. This file adds operational discipline for cases when there's no live human in the loop.

## When this applies

- An agent is explicitly told to operate "autonomously" or "until done."
- A PR is being opened by an automated process or scheduled job.
- The work will produce multiple commits before any human review.
- The maintainer is offline / will only see the result via the merged PR.

When in doubt, the **default is NOT autonomous mode**. Operate via `AGENTS.md` and ask for confirmation on high-risk decisions.

## 1. Issue-first workflow

Before changing any versioned file in autonomous mode:

1. Locate or create a `task issue` in GitHub.
2. Label it with at least `kind:task`, one `status:*`, one `priority:*`, one `area:*`, one `risk:*`, one `lane:*`.
3. Declare in the issue body:
   - `Owner atual`
   - `Lane oficial`
   - `Workspace da task`
   - `Write-set esperado`
   - `Classificacao de risco`
4. Create a worktree at `.claude/worktrees/<lane>/<issue-number>-<slug>/`.
5. Work in branch `task/<issue-number>-<slug>` (repo root stays on `main`).
6. Open a PR with `Closes #<issue-number>` in the body.
7. Complete via `scripts/pr_complete.ps1 -Pr <number>` or equivalent: wait for checks, merge, verify issue closure.
8. Update issue + docs before marking task complete.

## 2. Lanes

Official lanes:

- `lane:frontend` — `apps/desktop-web/**`
- `lane:backend` — `apps/api/**`, `src/**`, `desktop/**`, `tests/**`
- `lane:ops-quality` — `.github/**`, `docs/**`, root docs, operational scripts
- `lane:master` — cross-cutting execution lane with broad write access

**Rule:** `1 task = 1 owner = 1 branch = 1 worktree = 1 PR`.

A task belongs to exactly one lane. If the work genuinely spans two product lanes, split into separate child tasks.

## 3. Risk classifications

| Class | Definition | PR Setup |
|---|---|---|
| `risk:safe` | Isolated write-set | Open as ready |
| `risk:shared` | Touches shared files or critical-runtime paths | Open as **draft** |
| `risk:contract-sensitive` | Public API, DB schema, or public docs | Open as **draft** + document compatibility |

Critical-path classes are enforced by `.github/guardrails/path-policy.json`. Paths in `shared-governance`, `critical-bootstrap`, `critical-runtime`, or `critical-contract` require the matching `lane:*` and `risk:*`.

## 4. Parallel work protocol

- The protocol is per-task, not per-agent identity.
- If two tasks share write-set, one must wait, reduce scope, or be marked dependent.
- Record dependencies in the issue before continuing.
- During parallel work, public interfaces follow `additive-only` by default.
- Breaking contract changes require a dedicated `risk:contract-sensitive` task with serialized merge.

## 5. Child tasks between lanes

When your lane needs changes in another lane's write-set, open a formal child task instead of editing across lanes.

Child task body must include:

- `Task mae` (parent task number)
- `Lane solicitante` (your lane)
- `Criterio de consumo` (how the parent will verify the delivery)
- `Write-set esperado` (files the child lane will change)

While the child task is open or in review, the parent task is `status:blocked`. After the child merges, the parent moves to `status:awaiting-consumption`. Only the requester lane marks the delivery consumed and unblocks the parent.

## 6. Commit, push, merge policy

- Commit at coherent, validated checkpoints.
- Push when a checkpoint should be preserved remotely or reflected in the PR.
- Open the PR (even as draft) as soon as the branch is reviewable.
- When validations pass: update the issue, mark the PR ready if needed, and merge via `scripts/pr_complete.ps1` or equivalent.
- Preferred merge: **squash**.
- After merge: confirm task closure, remove the local worktree, confirm the remote branch was removed.

## 7. CI enforcement

In autonomous mode, the heavy guardrails are active:

- `.github/workflows/pr-issue-guardrails.yml` enforces the issue/PR contract when the PR carries the `flow:autonomous` label.
- `.github/guardrails/path-policy.json` enforces lane/risk constraints on critical paths.

For interactive PRs (no `flow:autonomous` label), these checks are skipped or relaxed.

## 8. Stop conditions

Autonomous mode stops immediately and requests human input when:

- A high-risk decision is reached (architecture, data model, auth, destructive ops).
- A critical-path file is touched without matching lane/risk authorization.
- A contract-sensitive breaking change is required.
- Tests fail and the failure isn't reproducible/explainable.
- The agent cannot validate the change against the project's success criteria.
