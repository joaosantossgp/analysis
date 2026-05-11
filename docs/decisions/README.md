# Architecture Decision Records

This directory holds the durable architectural decisions made on this project.

## How to read ADRs here

- ADRs are **historical decision records**. They capture the context, alternatives, and rationale that existed at the moment the decision was made.
- Some ADRs reference planning documents (e.g. `docs/STUDENT_PACK_PLAN.md`, `docs/WEBAPP_TRANSFORMATION_PLAN.md`, `docs/V2_PHASE1_BACKEND.md`, `docs/V2_PHASE2_WEB_SLICE.md`) that have since been **archived or removed** because they were point-in-time planning artifacts. The ADR itself is the canonical record of the decision — the planning docs were inputs to it.
- ADRs should **not** be interpreted as current operational instructions. For day-to-day rules, see [`../../AGENTS.md`](../../AGENTS.md). For active reference docs, see [`../reference/`](../reference/).
- If an ADR is superseded, the superseding ADR explicitly says so. Otherwise, the decision still stands.

## Index

| # | Title |
|---|---|
| [0001](0001-desktop-folder.md) | Desktop folder layout |
| [0002](0002-student-pack-v2-stack.md) | V2 stack with GitHub Student Pack |
| [0003](0003-v2-selection-criteria.md) | V2 framework selection criteria |
| [0004](0004-first-remote-runtime-railway-vercel.md) | First remote runtime: Railway + Vercel (later retired in favor of desktop) |
| [0005](0005-offline-governance-ledger.md) | Offline governance ledger pattern (used once for LT-0001; superseded by the simplified AGENTS.md flow) |
| [0006](0006-auth-desktop.md) | Authentication for the desktop app |
