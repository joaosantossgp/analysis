## Summary

<!-- 1-3 bullets: what changed and why. -->

Closes #

<!-- Use `Closes #n` for each task or bug this PR finishes (several are fine).
Use `Refs #n` for a goal or a related issue. The PR check takes the shipping
class from the `ships:*` labels of the closed issues (highest wins) and fails
when none has one. -->

## Documentation impact

<!-- Link the updated canonical owner docs, or explain why no documentation
update is needed. See the ownership matrix in
docs/PRODUCT_DEVELOPMENT_CHECKLIST.md#12-documentation-gate. -->

## Test plan

- [ ] `npm --prefix apps/desktop-web run typecheck` (UI TS/TSX edits)
- [ ] `npm --prefix apps/desktop-web run test` / `build` (UI behavior)
- [ ] `pytest tests/` (desktop/core edits)
- [ ] `pytest apps/api/tests/` (API edits)
- [ ] Verified in the real desktop runtime (UI/runtime edits)
- [ ] Unfinished parts of a larger implementation are unreachable in the app
      until the `ships:release` ticket lands (or N/A: nothing unfinished)

## Notes

<!-- Assumptions, risks, anything not validated. -->
