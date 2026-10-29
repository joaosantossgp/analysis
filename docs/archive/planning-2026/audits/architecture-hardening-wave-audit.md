# Architecture and Product Hardening Wave Audit

Date: 2026-07-28

Repository: `joaosantossgp/analisys`

Epic: https://github.com/joaosantossgp/analisys/issues/398

## Result

The package-validation evidence is complete for source/candidate commit
`4942992e2b5b8de072906380493b18871e9286b0`, pending PR CI, merge, and final
Epic reconciliation. Later harness-only CI portability edits on the PR branch
must not be treated as new packaged-runtime observations unless the package
harness is rerun.

The implemented children preserve the active Vite -> pywebview -> Python ->
local-store architecture. No task changed database schema, public bridge
behavior, financial calculations, release publication behavior, updater channel
policy, automatic startup metadata refresh behavior, broad `desktop/services.py`
structure, or product runtime behavior outside the approved validation harnesses
and guardrails.

Evidence classifications used below:

- PASS: direct evidence satisfies the requirement.
- CONTRADICTION: evidence proves a current behavior conflicts with a desired
  contract or previous assumption.
- INCOMPLETE: work or evidence is still required.
- WEAK: indirect or non-comparable evidence.
- MISSING: no qualifying evidence.

## Baseline

Authoritative design baseline commit:
`9ecd2db246668452262624ea7ad4f370eb7a67d9`.

Baseline environment: Windows NT `10.0.26200.0`, PowerShell `7.6.3`, Python
`3.11.9`, Node `v24.14.1`, Vite `6.4.2`.

The authoritative baseline counts are 688 core tests, 122 API tests, and 75
clean Vite tests. The previously observed 84 Vite count is not used as a
baseline because it came from a dirty interactive checkout.

Key baseline records are in
`docs/superpowers/specs/2026-07-21-architecture-product-hardening-wave-design.md`.
Each recorded row includes source SHA, exact command, environment, UTC
timestamp, duration, result, and log path.

## Child Summary

| Child | Issue | Result | Evidence |
| --- | --- | --- | --- |
| Design and plan | #398 / PR #406 | PASS | Merge `6a7482f8da23121c281cc4d306609c20edf09126` |
| Operational contract guardrails | #399 / PR #407 | PASS | Merge `8cda5d1f72d333ce4e144fcb3c76d930a4172755` |
| CI Vite/governance exposure | #400 / PR #408 | PASS | Merge `c49aba627ecd9f7b30e5b370db8dd29a712fc84f` |
| BridgeApi duplicate declarations | #401 / PR #409 | PASS | Merge `e8e70615d1ede3dd724b2a63da75e7ff2ae1fbfb` |
| Startup metadata refresh investigation | #402 | PASS characterization / CONTRADICTION / blocked | Reviewed issue evidence; no behavior change |
| Release-publication gate investigation | #403 | PASS characterization / CONTRADICTION / blocked | Reviewed issue evidence; no publication change |
| Bridge method inventory | #405 / PR #410 | PASS | Merge `c54d349b78e1dc9760e21abb43cae911d05e414f` |
| Current-head packaged candidate validation | #404 | PASS locally, pending PR/CI/merge | Branch head `4942992e2b5b8de072906380493b18871e9286b0` |

## Objective Audit

| Requirement | Classification | Evidence |
| --- | --- | --- |
| Verify repository/runtime/architecture/docs/issues/tests/packaging/data/performance evidence | PASS | Design baseline, child issue comments, merged PRs, #404 preflight, final package summary |
| Produce and save architecture health design and detailed plan | PASS | PR #406 merge `6a7482f8da23121c281cc4d306609c20edf09126` |
| Create one bounded Epic and 3-8 evidence-backed child issues | PASS | Epic #398 and children #399-#405 |
| Execute approved low/medium risk tasks in isolated worktrees | PASS | Children #399, #400, #401, #405 merged; #404 isolated branch |
| Preserve product behavior and architecture | PASS | Implemented diffs are guardrails/docs/harness only; no runtime product source modified by #404 |
| Preserve local-first/offline reads, downloaded data, source snapshots, lineage | PASS for observed package run | Final #404 source preservation step passed; source manifests byte-compared |
| Preserve bridge compatibility | PASS | #401 unique TypeScript bridge names preserved; #405 inventory records Python 150 / TS 143 / Python-only 7 / TS-only 0 / duplicates 0; #404 packaged bridge calls passed |
| Preserve Excel behavior | PASS for generated workbook validation | Final #404 workbook opened with openpyxl and Excel COM read-only |
| Preserve build/package/updater behavior | PASS for validation scope | Final #404 build, ZIP root, package launch, and scratch updater helper validation passed; no release published |
| Preserve existing performance unless measured improvements are delivered | PASS / WEAK for package startup comparison | Read-path microbenchmarks show no regression; packaged bridge readiness has no like-for-like baseline |
| Avoid broad rewrites, destructive/high-risk changes, feature expansion, stable releases | PASS | No schema, financial, release, startup-refresh, architecture, dependency, or user-visible behavior change |

## Child 7 Final Package Evidence

Child 7 branch: `task/404-current-head-package-validation`

Final source/candidate commit:
`4942992e2b5b8de072906380493b18871e9286b0`

Version: `0.30.0-rc.1`

Environment observed in the final package run: Windows, PowerShell, Python, Node
from the #404 worktree; exact environment and allowlist are recorded in
`scratch/architecture-hardening-wave/task-7/evidence-summary.json`.

Final package commands:

| Gate | Exact command | UTC start | Duration | Result | Log |
| --- | --- | ---: | ---: | --- | --- |
| Build candidate | `.\desktop\build_desktop.ps1 -Version $validationVersion` | `2026-07-28T15:58:19.7289289Z` | 144201 ms | PASS | `scratch/architecture-hardening-wave/task-7/20260728T155819Z-build-current-head.log` |
| Validate inputs | `pwsh -NoProfile -File scripts\diagnostics\validate_packaged_candidate.ps1 -Mode ValidateInputs -CandidateDir dist\CVMAnalytics -EvidenceDir scratch\architecture-hardening-wave\task-7 -SourceDataRoot C:\Users\jadaojoao\Documents\CVMAnalytics -CdCvm 9512 -CdpPort 9223` | `2026-07-28T16:00:43.9450520Z` | 1409 ms | PASS | `scratch/architecture-hardening-wave/task-7/20260728T155819Z-validate-inputs.log` |
| Mode Run | same harness with `-Mode Run` | `2026-07-28T16:00:45.3552049Z` | 333988 ms | PASS | `scratch/architecture-hardening-wave/task-7/20260728T155819Z-validation-run.log` |
| Four-file governance | `python -m pytest scripts/governance/test_repository_operational_contracts.py scripts/governance/test_frontend_ci_contract.py scripts/diagnostics/test_bridge_method_inventory.py scripts/governance/test_packaged_candidate_harness.py -q` | `2026-07-28T16:06:19.3571475Z` | 16662 ms | PASS, 36 tests | `scratch/architecture-hardening-wave/task-7/20260728T155819Z-post-run-governance.log` |

Final static checks before the package run:

| Gate | Command | UTC start | Duration | Result |
| --- | --- | ---: | ---: | --- |
| Diff whitespace | `git diff --check e472175..4942992` | `2026-07-28T15:57Z` | <1 s | PASS |
| PowerShell parser | Parser API on `scripts/diagnostics/validate_packaged_candidate.ps1` | `2026-07-28T15:57:46.0918077Z` | 57 ms | PASS, 0 errors |
| Node syntax | `node --check scripts/diagnostics/validate_packaged_ui.cjs` | `2026-07-28T15:57:46.0631567Z` | 63 ms | PASS |
| Four-file governance | same command as above | `2026-07-28T15:57:13.9376444Z` | 17570 ms | PASS, 36 tests |

Final build artifacts:

| Artifact | Value |
| --- | --- |
| Build info | `desktop/_build_info.py`: version `0.30.0-rc.1`, commit `4942992`, build time `2026-07-28T15:58:33Z` |
| Build info SHA-256 | `24DEE56820BE9DB7E99B0B5F3F939036E16DCC6A35C8B4D3EF2211FFF014EEF1` |
| Executable SHA-256 | `76C4B390CFF405320124815232A32E8EB0EA99FE97606A54402B4A0AE4570139` |
| Executable size | 24,393,038 bytes |
| Bundle files | 2,621 |
| Bundle bytes | 329,396,942 |
| ZIP SHA-256 | `84BD820861BB68476DC2D76FB79C742A09E87A38156719839F66E783D8215C4C` |
| ZIP size / entries | 123,829,998 bytes / 2,652 entries |
| ZIP root contract | PASS: flat roots `_internal` and `CVMAnalytics.exe` |

Final packaged runtime observations:

| Area | Result | Evidence |
| --- | --- | --- |
| Frozen diagnostic | PASS | Diagnostic PID `15404`, exit 0, version `0.30.0-rc.1` |
| Real WebView2/pywebview UI | PASS | UI PID `276`, Node child PID `18856`, cleanup confirmed |
| Bridge readiness | PASS | `bridge_ready_elapsed_ms` recorded in `ui/ui-results.json` |
| Bridge calls | PASS | `get_app_status`, `get_companies`, `get_company_info`, `get_company_financial_readiness`, `get_sin_kpi_dashboard`, `export_company_excel` all returned without top-level error |
| Bridge payloads | PASS | UTF-8 bytes: 4319, 4196, 949, 4680, 29499, 501 respectively |
| External network | PASS | 0 external network events; network log SHA `37517E5F3DC66819F61F5A7BB8ACE1921282415F10551D2DEFA5C3EB0985B570` |
| Console errors | PASS | 0 console errors |
| Screenshots | PASS | 8 PNG screenshots under `scratch/architecture-hardening-wave/task-7/ui/` |
| Refresh failure sentinel | PASS | synthetic `cd_cvm=999999` remained present with `cnpj=null` and `metadata_last_successful_refresh=null` after refused startup observation |
| Workbook | PASS | `PETR4_20260728.xlsx`, SHA `F3BB6BAC1F1A6DC00C34046E4F6586EC98C9CB6DBE873B65568129EB3D452AA9`, 79,082 bytes, 9 sheets, 2,297 formulas, openpyxl read and Excel COM read-only open succeeded |
| Scratch updater | PASS | Real `desktop/update_helper.ps1` exercised only against scratch current/staged dirs; staged/current/rollback hashes matched; relaunch marker `staged`; protected sentinels unchanged |
| Source preservation | PASS | `source_after_preservation`, fixture classification, and refresh-failure classification steps passed |
| Cleanup | PASS | Candidate/UI/probe/updater child cleanup recorded; no primary failure in final evidence summary |

Final screenshots:

- `scratch/architecture-hardening-wave/task-7/ui/empresas-1366x768.png`
- `scratch/architecture-hardening-wave/task-7/ui/empresas-1920x1080.png`
- `scratch/architecture-hardening-wave/task-7/ui/empresas-9512-1366x768.png`
- `scratch/architecture-hardening-wave/task-7/ui/empresas-9512-1920x1080.png`
- `scratch/architecture-hardening-wave/task-7/ui/indicators-section-energy-sub-sin-1366x768.png`
- `scratch/architecture-hardening-wave/task-7/ui/indicators-section-energy-sub-sin-1920x1080.png`
- `scratch/architecture-hardening-wave/task-7/ui/settings-diagnostics-1366x768.png`
- `scratch/architecture-hardening-wave/task-7/ui/settings-diagnostics-1920x1080.png`

Authoritative final summary:
`scratch/architecture-hardening-wave/task-7/evidence-summary.json`, status
`pass`, completed `2026-07-28T16:04:15.4281556Z`, summary size 271,883 bytes.

Post-audit CI portability note: after PR #411 exposed Linux PowerShell
governance failures, the harness was adjusted so `Start-Process -WindowStyle`
is applied only where supported, and Windows-only executable-compiler probes are
scoped to Windows. This is a validation-harness portability change only; it does
not change the packaged app or the recorded packaged-runtime observation above.

## Bridge Inventory

Final inventory document:
`docs/reference/bridge-method-inventory.md`.

Current classification from Child 4:

- Python methods: 150.
- TypeScript methods: 143.
- Python-only methods: 7.
- TypeScript-only methods: 0.
- TypeScript duplicate names: 0.

Residual Python-only methods are documented mismatches and were not corrected by
this wave because the approved scope was inventory and guardrail evidence, not
public-contract expansion.

## Startup Refresh Gate

Issue #402 remains blocked on explicit product approval.

Classification: PASS characterization / CONTRADICTION.

The investigation treats automatic startup CVM metadata refresh as a potential
local-first contract violation. It characterized dev and packaged behavior,
observability, failure semantics, database writes, opt-out behavior, and actual
consumers. No behavior was changed.

The #404 package run adds a bounded packaged observation: with an unmapped
synthetic sentinel `cd_cvm=999999`, refused startup leaves CNPJ and
`metadata_last_successful_refresh` absent. This proves the final harness can
observe the failure path without relying on Petrobras `9512`, whose CNPJ is
restored by local initialization from bundled mapping data.

## Release Publication Gate

Issue #403 remains blocked on explicit release-process approval.

Classification: PASS characterization / CONTRADICTION.

The investigation established that release publication is not currently gated on
the complete exact-SHA main CI evidence required by the proposed release gate.
No workflow, publication, tag, channel, or updater behavior was changed by this
wave.

## Performance

Comparable read-path baseline:

| Metric | Baseline `9ecd2db` | Child 7 preflight `c54d349` | Classification |
| --- | ---: | ---: | --- |
| cold `list_companies` | 690.45 ms | 560.57 ms | PASS, no observed regression |
| warm `list_companies` median | 0.00 ms | 0.00 ms | PASS |
| warm `search_petro` median | 0.01 ms | 0.01 ms | PASS |
| warm bridge `get_companies` median | 0.56 ms | 0.56 ms | PASS |
| warm bridge `get_base_health` median | 1.56 ms | 1.29 ms | PASS |

Packaged bridge readiness is recorded in the final UI artifact, but there is no
like-for-like packaged baseline. It is therefore not used to claim an
improvement or regression.

## Remaining Risks

- #402 startup metadata refresh remains a product decision. Changing or removing
  that behavior still requires explicit approval.
- #403 release-publication behavior remains a release-process decision. Changing
  it still requires explicit approval.
- Bridge Python-only methods are documented residuals, not fixed contracts.
- The final #404 branch still requires PR publication, CI, merge, and Epic
  reconciliation before the overall goal can be marked complete.
- The #404 sentinel correction received local static/code review and tests here;
  no additional subagent review was run after the user raised quota concerns.

## Prohibited Actions Check

No stable release was published. No tag was created. No updater channel was
changed. No database schema was modified. No public bridge contract was changed.
No financial calculation was changed. No automatic startup metadata refresh
behavior was changed. No broad `desktop/services.py` extraction was performed.
