## Summary

<!-- 1–3 bullets describing the scope and intent of this PR. -->

## Test plan

<!-- Checklist of validations run. Include relevant commands. -->

- [ ] `npx tsc --noEmit` (when web edits)
- [ ] `pytest tests/` (when src/ edits)
- [ ] `pytest apps/api/tests/` (when API edits)
- [ ] Manual verification in desktop mode (when UI/runtime edits)

## Notes

<!-- Optional: assumptions, risks, follow-ups. -->

---

<details>
<summary>Autonomous-mode PRs only</summary>

If this PR is part of an autonomous-agent workflow, also include:

- `Closes #<issue-number>`
- Lane: `lane:frontend | lane:backend | lane:ops-quality | lane:master`
- Risk: `risk:safe | risk:shared | risk:contract-sensitive`
- Worktree: `.claude/worktrees/<lane>/<issue-number>-<slug>/`
- Write-set:

See `docs/governance/autonomous-mode.md` for the full contract.

</details>
