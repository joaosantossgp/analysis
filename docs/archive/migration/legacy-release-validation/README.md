# Legacy Release Validation Scripts

Archived version-pinned MOTW + updater contract validation scripts from the
Phase 0 migration era. Both target specific published GitHub Release assets
that no longer represent the current product:

- `test_ci_v033_motw.ps1` — pinned to `v0.3.3` (insufficient ZIP layout; see
  `../PHASE_0_RELEASE_CHECKPOINT.md`).
- `test_ci_v034_full.ps1` — pinned to `v0.3.4` (first release with
  updater-compatible flat ZIP root).

These are kept for historical reference only. They are **not** the harness
to use for current releases.

## Current reusable MOTW validation

For any current release ZIP, use the reusable harnesses under `scripts/`:

```powershell
# MOTW launch reproduction
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_motw_launch.ps1 "C:\path\to\CVMAnalytics-windows-vX.Y.Z.zip"

# Explorer "Extract All" MOTW reproduction (stamps MOTW on every binary)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_motw_explorer.ps1 "C:\path\to\CVMAnalytics-windows-vX.Y.Z.zip"
```

See `../SMOKE_RECIPES.md` for the full validation recipe list.
