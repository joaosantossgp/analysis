# Phase 5 — Legacy Deletion (HISTORICAL PLAN)

> Note: this document was originally titled "Phase 3 — Legacy Deletion". After the Phase 4 default flip in `v0.14.0`, the canonical name for the legacy-deletion phase is **Phase 5**. The file path is kept for backward compatibility with old links.

Status: **Superseded by Phase 5A/5B/5C.** The desktop-side legacy runtime was
removed in `v0.15.0`. Do not use this older broad-deletion plan to remove
`apps/web/` or `apps/api/`; Phase 5C kept both as documented source-only /
hosted surfaces outside the desktop package and default desktop CI.

The original plan assumed Next.js, FastAPI, bundled Node, `apps/web/`, and
`apps/api/` could all be deleted together. Phase 5A narrowed that scope:
`apps/web/` and `apps/api/` are not desktop package dependencies and were kept.

Phase 3A through 3I were parity-planning and incremental screen-port phases.
Phase 3J was the readiness audit. Phase 4 shipped as `v0.14.0`: Vite became
the default. Phase 5B shipped as `v0.15.0`: the packaged desktop app became
Vite-only and no longer ships Node or Next standalone.

---

## Pre-conditions (all must be true)

1. ✅ **Vite SPA parity**: every P0 item in `PHASE_3_PARITY_MATRIX.md` is complete, and every production Next route has an equivalent Vite route exercised in a packaged build smoke. (Closed at `v0.13.0` / Phase 3I.)
2. ✅ **Default flip released**: Phase 4 / `v0.14.0` shipped with Vite as the default and Next as opt-in via `--legacy`. Both UIs still bundled.
3. ⏳ **Soak window**: the `v0.14.0` default-Vite release must run on real machines for at least one soak window (1–2 weeks) without unresolved Vite-default regressions.
4. ⏳ **Manual sign-off from the user**: explicit "OK to delete Next / Node / FastAPI".
5. ⏳ **No regression** in the Phase 0 contract (Documents DB, MOTW strip, updater allowlist, recovery scenarios) after switching default to Vite.

If any pre-condition is not met, **do not start Phase 5**.

---

## Scope of deletion

The following are candidates for removal once Vite reaches parity:

### Bundle deletions
- `_internal/web_standalone/` (26 MB)
- `_internal/node.exe` (88 MB)

### Repo deletions
- `apps/web/` (entire Next.js project)
- `apps/api/` (entire FastAPI project)
- `desktop/node_portable/` (build artifact dir)

### Packaging deletions
- `desktop/app.spec`:
  - Remove `STANDALONE_DIR` data entry.
  - Remove `NODE_EXE` data entry.
  - Optionally rename `desktop-web` → `web` for the resulting `_internal/web/` path.
- `desktop/build_desktop.ps1`:
  - Remove `next build` step.
  - Remove `node.exe` portable copy step.
  - Remove the static asset copy step (`public/` + `.next/static/` → `standalone/`).
- `.github/workflows/release-desktop.yml`:
  - Remove `setup-node` + `npm ci --prefix apps/web` steps.
  - Verify `desktop/build_desktop.ps1` no longer needs Node.

### Runtime deletions
- `desktop/app.py`:
  - Remove the `--legacy` branch in `main()` (the Vite default is already in place from Phase 4).
  - `--dev` branch removed (or repurposed for Vite dev server).
  - Remove `_web_dir`, `_standalone_path`, `_node_exe`, `_npm_cmd`, `_start_dev_server`, `_start_standalone_server`.
  - Remove the `_DEV_PORT`, `_DEV_URL` constants.
- `requirements.txt` / `apps/api/requirements*.txt`:
  - Remove FastAPI, Uvicorn, Sentry (if not used elsewhere).

### Docs deletions / updates
- Update `README.md` to drop references to Next / Node / FastAPI as part of the runtime.
- Mark `docs/migration/PHASE_*` as historical.
- Update `apps/desktop-web/README.md` to remove "still parallel to Next" disclaimers.

---

## Suggested execution order

Each step is a separate commit. Easier to revert one step if smoke fails.

1. ✅ **Verify parity matrix.** Done at `v0.13.0` / Phase 3I.
2. ✅ **Default flip.** Shipped as `v0.14.0` / Phase 4. Vite default; Next reachable via `--legacy`. Both UIs still bundled.
3. ⏳ **Soak window.** 1–2 weeks against `v0.14.0`. Watch issue tracker. If users report Vite-default bugs, fix and re-soak. **Do not proceed unless the soak is clean.**
4. **Remove `--legacy` runtime path from `desktop/app.py`.** Single commit: deletes the `legacy_mode` branch, `_start_standalone_server`, `_start_dev_server`, `_standalone_path`, `_node_exe`, `_npm_cmd`, `_DEV_PORT`, `_DEV_URL`, and the `--legacy`/`--dev` flag parsing. `--vite` becomes a no-op alias or is also removed.
5. **Remove Node + web_standalone from `app.spec` + build script.** Single commit. Bundle drops ~114 MB.
6. **Delete `apps/web/`.** Single commit. Big diff. CI workflow update.
7. **Delete `apps/api/`.** Single commit. Update `requirements.txt` family.
8. **Delete `desktop/node_portable/`.** Trivial.
9. **Update docs and release `vX.Y.1`.** Mark phase tracker complete.
10. **Phase 6 starts.** Code signing, AV/UPX review.

---

## Safety nets that MUST survive Phase 3

Even after deletion, these contracts remain inviolable:

- LOCALAPPDATA user-data layout (`db/`, `output/`, `logs/`, `cache/`).
- `desktop/app.py::_migrate_legacy_db_once` + `_wal_safe_copy_sqlite` (handles upgraders coming from older releases that may still have install-dir DBs).
- `desktop/update_helper.ps1` allowlist + rollback snapshot.
- `desktop/app.py::_strip_motw_from_bundle` (still needed; not Next-specific).
- `desktop/app.py::_preflight_pywebview_backend` (still needed; checks .NET Framework / WebView2 / pythonnet runtime files).
- `desktop/app.py::_run_diagnostic_mode` (still needed for user bug reports).
- `desktop/updater.py` (still needed for auto-updates).
- Auto-updater asset naming contract (`CVMAnalytics-windows-vX.Y.Z.zip` + `.sha256`).
- CI flat-zip-root verification (`Compress-Archive -Path dist\CVMAnalytics\*`).

If any of these break during Phase 3, **revert the offending commit** and re-plan.

---

## Risk register

| Risk | Mitigation |
|---|---|
| Vite SPA missing a feature only present in Next route | Parity matrix in pre-condition 1; soak window |
| User on very old release (`v0.2.x`) auto-updates and their bundled Node assumption breaks | Updater allowlist swap is the same; their install becomes the new Vite-only bundle on next launch |
| User-data migration regression | Phase 0 migrator unchanged; covered by smoke tests |
| Removing `apps/api/` breaks some CLI / scripted workflow | Audit before delete: grep for `from apps.api`, `uvicorn apps.api`, `apps/api/worker.py`, `railway.toml`, `apps/api/Dockerfile`. Document any non-desktop users. |
| Removing FastAPI from `requirements.txt` breaks `apps/web/` build (during the transition where Vite is default but apps/web/ still exists) | Sequence carefully: delete `apps/api/` only after step 6 (Next deletion) which removes the consumer. |
| CI workflow Node step removal breaks something | Verify `desktop/build_desktop.ps1` does not still call `npm ci` against `apps/web/`; remove all `apps/web/` references in same commit. |
| Bundle size win unexpectedly small | Run `du -sh dist/CVMAnalytics/_internal/*` after deletion; if not ~114 MB lower, investigate. |

---

## Do NOT do during Phase 3

- Rewrite git history.
- Force-push.
- Skip the soak window.
- Combine deletion commits into one mega-commit.
- Delete a directory without first grepping the repo for cross-references.
- Touch user-data contracts.
- Touch the updater allowlist.
- Remove `_preflight_pywebview_backend` even though Next is gone — pythonnet is still required for pywebview's WinForms backend.
- Remove `_strip_motw_from_bundle` — still required for `Python.Runtime.dll` to load.
