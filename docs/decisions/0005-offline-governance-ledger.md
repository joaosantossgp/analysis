# ADR 0005 - Offline governance ledger during GitHub outage

- Status: superseded by the [issue-driven workflow in AGENTS.md](../../AGENTS.md#5-workflow)
- Date: 2026-04-12

This is a historical record. GitHub Issues and PRs now own work tracking under
the linked workflow; the temporary ledger below is not an active fallback.

## Context

The repository's operating contract relied on GitHub Issues, branches, worktrees
and PRs for backlog management and traceability. During a temporary interruption
of that workflow, the project still needed:

- work organization
- change traceability
- clear write sets and ownership
- durable decision records
- a clear migration path back to GitHub

Without a minimal local structure, the repository root could become a mixture of
chat context, code changes and implicit decisions that were hard to reconstruct.

## Historical decision

While Git/GitHub were outside the operational workflow, the decision was to use
a local ledger in `docs/local-ops/` with these rules:

- `INDEX.md` served as the temporary local backlog and offline source of truth
- each local task received a stable `LT-####` ID
- each local task declared an owner, lane, offline workspace, write set, risk
  and future mapping to a GitHub issue
- operational evidence lived in `docs/local-ops/evidence/<task-id>/`
- durable decisions remained in `docs/decisions/`
- `.ai-activity.log` remained an append-only trail of executed changes

## Consequences

### Benefits

- reduced rework and context loss during the offline period
- distinguished the local backlog, durable decisions and execution trail
- made future issues easier to create without repeating completed investigations

### Costs

- required manual discipline to keep the ledger and evidence current
- did not replace branches, worktrees or PRs; it only reduced disorder while
  they were unavailable

## Historical return plan

The return to GitHub was planned as follows:

1. Convert each relevant `LT-####` into a formal issue.
2. Link the issue to the evidence accumulated locally.
3. Record the corresponding issue number, branch and PR in the local ledger.
4. Archive the local task only once the migration was clear.
