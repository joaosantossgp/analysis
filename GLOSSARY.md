# CVMAnalytics

A local-first analyst workbench for Brazilian listed companies. Its data comes
from official CVM filings and is stored and read on the analyst's machine.

## Language

### Local data

**Local database**:
All company data stored on the analyst's machine. It stays readable offline.
_Avoid_: base, the database (unqualified), cache

**Data update**:
An explicit, logged run that fetches official CVM filings into the local
database. It is never started implicitly by opening a screen.
_Avoid_: Database Updates, Data Updates, Update Database, Update Base, sync

**Company update**:
A data update limited to a single company.
_Avoid_: on-demand refresh, Update data (for this scope)

**Stale**:
The state of the local database when a CVM filing deadline (ITR or DFP) has
passed since the last successful data update covering all active companies, so
newer filings may exist. Company updates and retries do not reset it.
_Avoid_: outdated, old, out of sync

**History range**:
The span of past fiscal years that a data update fetches.
_Avoid_: period (reserved for statement periods), year range, window

**Data completeness**:
Whether the local database holds usable statements for a given company and
period.
_Avoid_: coverage (for this meaning), health, gaps

### Analyst work

**Coverage universe**:
The set of companies an analyst has chosen to cover.
_Avoid_: universe (for the set of companies a data update fetches), preset

### Publishing

**Publication**:
One numbered build of `main` made available to installed apps. Every publication contains everything published before it.
_Avoid_: Drop, deploy

**Pre-release**:
A publication offered only to users who opted into the pre-release update channel.
_Avoid_: RC, release candidate, beta, nightly

**Release**:
A publication offered to every installed app.
_Avoid_: Stable, final, latest

**Promotion**:
Turning an existing pre-release into a release without rebuilding or renumbering it.
_Avoid_: Re-release, graduate

**Update channel**:
The user's choice of which publications their installed app accepts: releases only, or pre-releases and releases.
_Avoid_: Track, ring

**Shipping class**:
The label on an issue that says what its merge publishes: `none`, `pre`, `release` or `hotfix`.
_Avoid_: Release type, bump label

**Risk area**:
A part of the codebase whose changes need the owner's packaged test before publication: the desktop shell and updater, packaging, dependencies, database schema or migrations, and ingestion.

**Candidate**:
The exact packaged file built by CI for a publication, before it is published.
_Avoid_: Artifact, bundle

**Installed app**:
The packaged CVMAnalytics on a user's machine, which updates itself from publications.
_Avoid_: Release app, production app

### Development

**Dev mode**:
The desktop app run from source with `--dev`, used by the owner as the always-open development window.
_Avoid_: Dev runtime, debug mode

**Dev panel**:
The floating control, present only in dev mode, that opens development functions such as worktree switching and dev data actions.
_Avoid_: Dev pin, dev settings, debug menu

**Worktree switch**:
Pointing the open dev mode window at another git worktree's code.

**Shared dev data**:
The dev data folder of the main checkout, used by every worktree that is not data-sensitive.
_Avoid_: Default data, common data

**Isolated dev data**:
A worktree's own copy of the dev database, used when its work could alter or break shared dev data.
_Avoid_: Sandbox data, private data

**Data-sensitive worktree**:
A worktree whose issue touches database schema, migrations, ingestion, refresh or reset, and therefore runs on isolated dev data.

**Dev data backup**:
The single previous copy of dev data kept when the current one is reset from the dev panel.
