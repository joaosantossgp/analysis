# Release Notes Index

This directory holds per-version release notes for the CVMAnalytics desktop product.

The **current stable baseline is `v0.18.2`** (analyst-ready Excel export patch). The packaged Windows desktop EXE distributed via [GitHub Releases](https://github.com/joaosantossgp/analisys/releases) is the authoritative distribution channel — this directory is a **partial** local copy of the per-version notes, not the source of truth.

## Current

| Version | Notes |
|---|---|
| `v0.18.2` | [v0.18.2.md](v0.18.2.md) — current stable, analyst-ready Excel export |
| `v0.18.1` | [v0.18.1.md](v0.18.1.md) — Terminal UI patch |
| `v0.18.0` | [v0.18.0.md](v0.18.0.md) — Terminal UI release |

## Historical (release notes present)

| Version | Phase / theme | Notes |
|---|---|---|
| `v0.17.0` | Phase 6 — final product hardening | [v0.17.0.md](v0.17.0.md) |
| `v0.16.0` | Phase 5C — source-only legacy cleanup | [v0.16.0.md](v0.16.0.md) |
| `v0.15.0` | Phase 5B — Node/Next removed from desktop bundle | [v0.15.0.md](v0.15.0.md) |
| `v0.14.1` | Hotfix — GICS backfill | [v0.14.1.md](v0.14.1.md) |
| `v0.14.0` | Phase 4 — Vite as default | [v0.14.0.md](v0.14.0.md) |
| `v0.11.0` | Phase 3G — status / updater / diagnostics UI | [v0.11.0.md](v0.11.0.md) |
| `v0.10.0` | Phase 3F — single-company refresh controls | [v0.10.0.md](v0.10.0.md) |
| `v0.2.0` | Early baseline | [v0.2.0.md](v0.2.0.md) |

## Release evidence and templates

| File | Purpose |
|---|---|
| [desktop-hardening-evidence-2026-05-08.md](desktop-hardening-evidence-2026-05-08.md) | Dated build-hardening evidence record |
| [on-demand-hardening-evidence-template.md](on-demand-hardening-evidence-template.md) | Reusable template for on-demand release evidence |

## Coverage gaps (release notes not present here)

Tagged releases that exist on GitHub but do **not** have a local `.md` file under `docs/releases/`:

- `v0.3.0`, `v0.3.1`, `v0.3.2`, `v0.3.3`, `v0.3.4` — Phase 0 user-data safety + updater contract iterations
- `v0.4.0` — Phase 2 packaged exe with Vite static
- `v0.5.0` — Phase 3A financial statements
- `v0.6.0`, `v0.6.1` — Phase 3B update-base parity
- `v0.7.0` — Phase 3C persistent Documents data root
- `v0.8.0` — Phase 3D sectors + filters
- `v0.9.0` — Phase 3E Excel export
- `v0.12.0` — Phase 3H navigation polish + KPI charts
- `v0.13.0` — Phase 3I statement export scope + updater UI

For these versions, the authoritative notes are on the corresponding [GitHub Release](https://github.com/joaosantossgp/analisys/releases) page. This directory is **milestone-only coverage** rather than a full release log. Backfilling from `git tag --format='%(contents)' <tag>` is an open decision — see `docs/reference/repository-map.md`.

## Conventions

- One file per published version: `vX.Y.Z.md`.
- Filename matches the git tag exactly.
- New versions: add a new file; do not overwrite past notes.
- For per-release validation evidence, use the `on-demand-hardening-evidence-template.md` template and date the resulting file.
