## Summary

<!-- 1-3 bullets: what changed and why. -->

Closes #

<!-- Use `Closes #n` for each task or bug this PR finishes (several are fine).
Use `Refs #n` for a goal or a related issue. -->

## Test plan

- [ ] `npm --prefix apps/desktop-web run typecheck` (UI TS/TSX edits)
- [ ] `npm --prefix apps/desktop-web run test` / `build` (UI behavior)
- [ ] `pytest tests/` (desktop/core edits)
- [ ] `pytest apps/api/tests/` (API edits)
- [ ] Verified in the real desktop runtime (UI/runtime edits)

## Notes

<!-- Assumptions, risks, anything not validated. -->
