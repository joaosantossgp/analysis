# Documentation, architecture and governance audit

Date: 2026-11-16. Repository baseline: `23c2f59`.
Status: dated assessment; first-round delivery authorized separately below.
Scope: repository organization, documentation freshness, GitHub governance and CI.
Remote observations are a dated snapshot of `joaosantossgp/analysis`.
Source citations are pinned to the audited commit so later fixes preserve this record.

Delivery note (2026-11-16): the owner authorized publication (#509), documentation
reconciliation (#510) and the development-data ignore rule (#511). Remote protection
options are tracked for owner decision in #512; no plan purchase or settings change
is authorized. Later CI and architecture recommendations remain proposals.

## Assessment

Preserve the architecture and the core governance workflow. The repository already
separates the desktop shell, packaged frontend, Python core, HTTP adapter, tests,
tooling and historical material. Its operating rules identify canonical documents
and require evidence before describing a workflow as implemented.
See [entry rules](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/AGENTS.md#L9), [runtime boundaries](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/architecture.md#L21)
and the [repository map](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/reference/repository-map.md#L15).

The main improvement is to make existing rules and descriptions agree with current
code and remote enforcement. Another top-level hierarchy, a new approval framework
or a broad code move would add work without addressing the observed gaps.
The highest-priority discrepancy concerns release protection; the most immediate
local hygiene gap concerns generated development data.

The canonical index, explicit historical banners and issue/PR workflow are useful.
Keep the current distinction between product direction, implemented behavior and
dated validation. The [documentation gate](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/PRODUCT_DEVELOPMENT_CHECKLIST.md#L300)
already supplies most of the update policy needed.

## Observed baseline

- The checkout contains 166 tracked documentation Markdown files: 46 under archive,
  45 under releases and 20 at the documentation root. Volume alone is not a defect.
- The authenticated GitHub query returned no open issues at audit time; the current
  [issue list](https://github.com/joaosantossgp/analysis/issues) is time-sensitive.
- The latest 35 inspected Actions runs succeeded. Current
  [main CI](https://github.com/joaosantossgp/analysis/actions/runs/43920472106) and
  [PR #508 CI](https://github.com/joaosantossgp/analysis/actions/runs/43919975103)
  include Python/API, coverage, frontend tests/typecheck/build and Windows storage checks.
- The latest [desktop release run](https://github.com/joaosantossgp/analysis/actions/runs/29464970801)
  is from July 16 and predates the current release workflow. It does not prove that
  the present candidate/attestation/publication pipeline has completed successfully.

## Ranked findings

### 1. High: documented remote release protections are not established

[Build/release](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/build-release.md#L76) and [release process](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/release-process.md#L93)
describe a reviewer and protected-main environment gate. Authenticated API inspection
returned `main.protected=false`, protection disabled and no required status checks;
every branch in the paginated branch inventory was unprotected. Protection/ruleset
endpoints returned HTTP 403 with an upgrade-or-public-repository message.
Sources: [main branch API](https://api.github.com/repos/joaosantossgp/analysis/branches/main)
and [branch inventory API](https://api.github.com/repos/joaosantossgp/analysis/branches).

The [release-publication environment API](https://api.github.com/repos/joaosantossgp/analysis/environments/release-publication)
returned `can_admins_bypass=false`, but its only protection rule was `branch_policy`;
there were no required reviewers. Its policy selected protected branches and no
custom branch rules. GitHub documents that this setting allows all branches when
none are protected. Consequently, it does not establish the documented main-only
restriction. Workflow-level checks remain separate safeguards.
See [environment semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).

Reconcile the intended gate with the account's actual capabilities before relying
on these statements for a release. Assess plan eligibility or explicitly document
the manual approval procedure and its limitations. GitHub Pro can enable private
branch protection, but it does not by itself establish availability of required
environment reviewers for a private repository. See
[branch availability](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
and [environment plan limits](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).
No remote configuration changes or release attempt were made in this audit.

### 2. High: the default development data root is not ignored

[The runtime](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/desktop/app.py#L129) writes isolated development data under
`data/dev-runtime/`; [.gitignore](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/.gitignore#L11) covers other data roots but
has no rule for this root. `git check-ignore --no-index` did not match representative
financial database, raw ZIP or refresh-state paths there; an equivalent `data/db/`
path matched. This creates an avoidable accidental-staging risk after normal dev use.
Add a narrowly scoped ignore rule in a future change; do not delete or relocate data.

### 3. Medium: active capability descriptions contradict current routes

[Product workflows](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/product-workflows.md#L31) still uses `/coverage` as the
workflow address and lists reading collected News through `/news`.
[Product direction](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/PRODUCT_DIRECTION.md#L504) also lists an active News route.
The [router](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/apps/desktop-web/src/App.tsx#L149) instead mounts Coverage under
Companies, redirects old Coverage URLs and renders a retirement notice for News.
[Architecture](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/architecture.md#L147) correctly distinguishes retired News UI
from preserved backend/data. Reconcile these descriptions in one documentation change.
[News source documentation](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/data-sources.md#L147) should likewise distinguish
retained `NewsPage.tsx` text from evidence about the mounted UI.

### 4. Medium: issue guardrails validate closing references but not linked references

The [workflow](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/.github/workflows/pr-issue-guardrails.yml#L31) accepts `Refs`
syntax, but its API lookup loop checks only closing references. Executing its embedded
JavaScript with a mocked GitHub API showed that a nonexistent `Refs #n` can pass.
Validate existence and issue-versus-PR identity for both reference classes, while
retaining the rule that goals are referenced rather than closed automatically.
Also align the [goal template](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/.github/ISSUE_TEMPLATE/goal.yml#L3), which only
adds `goal`, with the [new-issue needs-triage rule](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/AGENTS.md#L93).

### 5. Medium: CI has redundant work and a limited workflow-contract test

[The ordinary Python job](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/.github/workflows/ci.yml#L35) and
[coverage job](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/.github/workflows/ci.yml#L61) both run `tests apps/api/tests`.
Consider one full run with coverage before adding elaborate documentation-only skip
logic. This could reduce runner consumption; elapsed-time savings were not measured.

The [frontend contract parser](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/scripts/governance/test_frontend_ci_contract.py#L10)
extracts named run commands but does not evaluate `if` or `continue-on-error`.
An in-memory `if: false` mutation left its parsed result unchanged. Strengthen this
small contract so it catches disabled or nonblocking required steps; the observed
current CI does execute the frontend checks successfully.

### 6. Medium: current status and lifecycle metadata have drifted

[STATUS](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/STATUS.md#L3) requests a one-screen snapshot but has 124 lines;
its [Active work](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/STATUS.md#L28) mostly recounts delivered or closed work and
detailed benchmarks. Keep current work, release state, decisions and limitations
there, linking to the existing evidence records for completed investigations.

[Repository profile](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/REPOSITORY_PROFILE.md#L3) still names the old repository
and [Vercel homepage](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/REPOSITORY_PROFILE.md#L11), including an actionable update
command. The current [repository API](https://api.github.com/repos/joaosantossgp/analysis)
reports `joaosantossgp/analysis` and `https://joaosantossgp.github.io/analysis/`.
Reconcile this document or mark it historical.

[ADR 0005](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/decisions/0005-offline-governance-ledger.md#L3) says accepted while
[its index](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/decisions/README.md#L20) says superseded. Update the individual status
and successor pointer, preserving the original reasoning. Existing
[withdrawn banners](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/reference/entity-registry-baseline.md#L3) are a useful pattern.

### 7. Lower: ownership can be clearer without moving everything

The [folder map](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/reference/repository-map.md#L82) calls all research proposals,
although [financial QA validation](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/research/2026-11-11-financial-qa-validation.md#L3) records
an implemented contract. Clarify evidence categories and include governance/testing
and tracked `.superpowers/` investigation notes in the map. Preserve existing paths.

[CountryKpisPage](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/apps/desktop-web/src/routes/CountryKpisPage.tsx#L109) exports
Companies and Settings surfaces. Extract them when a substantive change benefits
from explicit ownership. A [core property importing desktop services](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/src/financials/read_service_query.py#L179)
also deserves review when touched, but symbol search found no callers; this is not
evidence of an active runtime failure. Neither observation warrants a mass refactor.

There is a more concrete service boundary to improve when that behavior next changes:
[the status bridge](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/desktop/bridge_api/status.py#L1488) computes data coverage
using direct SQL and a service's private method. Extracting that cohesive operation
behind a public service would clarify responsibility while preserving bridge names.
The [API description](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/apps/api/app/main.py#L69) also still says read-only even
though its [refresh endpoint](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/apps/api/app/routes/refresh.py#L88) dispatches writes;
correct the metadata in a separately scoped API change.

## Folder responsibilities: retain locations, clarify authority

| Location | Current role | Recommended clarification |
|---|---|---|
| `desktop/` | Shell, bridge, packaging, updater | Keep host integration here. |
| `apps/desktop-web/` | Only packaged UI | Organize by owning workflow when editing meaningful behavior. |
| `src/` | Python domain/data behavior | Keep reusable core independent of the desktop host. |
| `apps/api/` | HTTP adapter and tests | Preserve as an adapter, not a second product UI. |
| `scripts/`, `tests/` | Tooling and verification | Keep runtime code out of one-off investigative helpers. |
| `docs/` root | Canonical product/runtime/domain/operation contracts | Link to one owner for each detailed rule. |
| `README.md`, `docs/STATUS.md` | Entry index and current snapshot | Keep summaries short; link to contracts and dated evidence. |
| `docs/reference/` | Operational and module reference | Clearly mark withdrawn records individually. |
| `docs/decisions/` | Decisions and their rationale | Maintain current status and superseding references. |
| `docs/research/`, `governance/`, `perf/`, `diagnostics/`, `testing/` | Research and validation evidence | Explain purpose, baseline, date and authority; do not imply all are proposals. |
| `docs/archive/`, `releases/`, `vendor/` | History, release notes and external source material | Preserve provenance; GitHub Releases owns published release state. |
| `data/`, generated roots | Source assets plus local runtime outputs | Distinguish tracked inputs from ignored generated data. |
| `.agents/skills/`, `.superpowers/` | Vendored skills and investigation material | Map both; keep skill updates explicit and manual. |

The current [folder inventory](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/reference/repository-map.md#L70) is the owner of
this map. The table above proposes clarification, not approved moves or deletions.

## Per-PR documentation update matrix

| Change | Owning documentation | Minimum update |
|---|---|---|
| Route/navigation/workspace behavior | `architecture.md`, `product-workflows.md`; map if needed | Actual route, redirect/retirement, owning workflow and evidence. |
| Workspace ownership or UI interaction guidance | `PRODUCT.md`, `DESIGN.md` | Update affected principles and patterns; link to the route inventory. |
| Product direction or admission rule | `PRODUCT_DIRECTION.md`; `STATUS.md` for major decisions | Decision and boundaries; keep future and implemented separate. |
| Financial/source/storage behavior | `CONTEXT.md`, `data-sources.md`, relevant module reference | Source, units, periods, lineage, persistence and failure/offline effects. |
| Setup, dev flags or paths | `development.md`, detailed data-path reference | Reproducible command, path precedence and isolation. |
| Workbook behavior | `excel-exports.md` | Output contract and appropriate validation evidence. |
| Build/updater/publication | `build-release.md`; short release pointer and status if changed | Artifact/provenance contract and actual remote gate assumptions. |
| Governance or CI | `AGENTS.md`/agent docs and matching templates/tests | Rule and enforceable behavior agree. |
| Completed experiment | Existing evidence folder | Date, baseline, scope, method, results and unvalidated limits. |
| Internal change without documentation impact | PR description | State the reason; do not rewrite unrelated contracts. |

This extends the existing [documentation gate](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/PRODUCT_DEVELOPMENT_CHECKLIST.md#L300).
Add one brief documentation-impact field to the [PR template](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/.github/PULL_REQUEST_TEMPLATE.md#L18).
Reconcile its required minimum with the [vendored PR skill](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/.agents/skills/pr/SKILL.md#L12)
through the repository contract; do not silently modify pinned upstream instructions.

## Minimal maintenance routine and suggested sequence

For each PR, identify the owning contract, update affected claims alongside code,
check changed local links and confirm that status/limitations remain accurate.
Before merge, compare stated validation with actual CI/runtime evidence. On a release,
also re-read remote protection configuration; YAML alone cannot prove its state.
When retiring a workflow or decision, update its entry points and individual status
together. Avoid a second backlog in STATUS or a calendar-driven rewrite of all docs.

1. **First:** resolve the documented-versus-remote release gate and isolate generated
   dev data from Git. These are independent findings with separate scope/validation.
2. **Next:** reconcile News/Coverage/profile/ADR/STATUS text and the documentation map.
   Add the small PR documentation-impact convention and local link check.
3. **Then:** tighten issue/CI contract checks and consolidate repeated Python execution,
   preserving required checks and coverage evidence. Measure before claiming savings.
4. **On relevant feature work:** improve component ownership or dormant dependencies
   only where the change has a concrete maintenance benefit.

These priorities describe the assessment. The delivery note above identifies the
subsequently authorized first round; it does not authorize remote settings changes. Keep the existing issue/PR/CI workflow
and [manual skill maintenance](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/agents/skills.md#L101).

## Verification performed and limits

Executed: read-only source/doc inventory; authenticated GitHub metadata, issue,
branch, environment and Actions inspection; ignore-rule probes; embedded issue-guard
mock execution; in-memory frontend-parser mutation; offline vendored-skill verification.
The [recent skill check](https://github.com/joaosantossgp/analysis/actions/runs/42110380772)
also succeeded. These checks do not establish fresh packaged-runtime acceptance.

A restricted Markdown check examined 36 files and 109 local link targets, excluding
fenced code, with zero missing target files. A broader nonarchive/nonvendor check
covered 122 files and 216 targets, also with zero missing files. This does not check
anchors, external URLs or semantic accuracy. Stale News claims demonstrate that limit.

The audit itself did not launch the app, ingest or access user data, run a full test
suite, build or publish a release, commit changes or mutate remote settings. Publication
of this report and follow-up work are tracked separately in the delivery note. The historical [failed refresh run](https://github.com/joaosantossgp/analysis/actions/runs/30695642272)
does not establish current external-database health; [scheduled refresh disablement](https://github.com/joaosantossgp/analysis/blob/23c2f59d8a1e139db29390594f362834e7d33dcd/docs/STATUS.md#L23)
is documented separately. Current release execution, protected publication behavior
and any runtime effects of the lower-priority code observations remain **Needs validation**.
