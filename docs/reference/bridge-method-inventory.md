# Desktop Bridge Method Inventory

Provenance:

- Inventory execution and reviewed tool/report commit SHA: `019bc4560563df868656adfa831fc7b5cb60ceb7`
- Runtime bridge and TypeScript declaration base SHA: `e8e70615d1ede3dd724b2a63da75e7ff2ae1fbfb`
- Command: `python scripts/diagnostics/bridge_method_inventory.py --root .`
- Environment: Microsoft Windows NT 10.0.26200.0; PowerShell 7.6.3; Python 3.11.9; Node v24.14.1; npm 11.11.0
- Working directory: `C:\Users\jadaojoao\Documents\Projects\analisys\.claude\worktrees\ops-quality\405-bridge-method-inventory`
- Timestamp (UTC): `2026-07-22T00:17:12.9148482Z`
- Duration: 0.154 seconds
- Result: PASS (exit code 0)
- Ignored inventory artifact: `scratch/architecture-hardening-wave/task-4/review-committed-bridge-method-inventory.json`
- Ignored classification evidence: `scratch/architecture-hardening-wave/task-4/review-active-vite-mismatch-search.log` and its provenance JSON, `review-python-mismatch-source-search.log`, and `review-legacy-nextjs-shim-evidence.log`
- Source state: committed and clean. The reviewed inventory tool and mismatch classifications were committed at the inventory execution SHA; the Python runtime bridge and TypeScript declarations were unchanged from the stated base SHA.

## Inventory summary

| Measure | Verified count |
| --- | ---: |
| Public Python `CVMBridge` mixin methods | 150 |
| Unique TypeScript `BridgeApi` methods | 143 |
| Python-only methods | 7 |
| TypeScript-only methods | 0 |
| Duplicate TypeScript declarations | 0 |

Both sides exceed 100 methods and include `ping`, `get_companies`, and
`export_company_excel`. The ignored JSON artifact contains the complete sorted
method lists and mismatch lists.

## Python-only methods

Every name below was searched in the active Vite source for a `callBridge`
consumer and in Python source and tests. None has an active Vite `callBridge`
call site.

| Method | Classification | Verified evidence |
| --- | --- | --- |
| `download_company_excel` | Needs separately approved follow-up | Defined in `desktop/bridge_api/companies.py`; no active Vite or Python-test reference. It returns a base64 browser-download payload while the active Vite export path calls the typed `export_company_excel` method, but the retained bridge method's intended status is not documented. |
| `get_company_suggestions` | Active Python-only method | Defined in `desktop/bridge_api/companies.py` and directly exercised by `tests/test_backend_perf_optimizations.py`; no active Vite reference. |
| `get_em_destaque` | Needs separately approved follow-up | Defined in `desktop/bridge_api/companies.py`; no active Vite or Python-test reference. History shows that it entered through the former Next.js bridge shim and the same service operation remains exposed by `apps/api/app/routes/companies.py`, but there is no current evidence of intentional bridge retention. |
| `get_plant_parcel_source_submarket_summary` | Needs separately approved follow-up | Defined in `desktop/bridge_api/energy.py`, and its underlying service operation is exercised by `tests/energy_kpi/test_plant_parcels.py`. There is no direct bridge test, TypeScript declaration, or active Vite call site, so the intended bridge exposure cannot be inferred. |
| `get_populares` | Needs separately approved follow-up | Defined in `desktop/bridge_api/companies.py`; no active Vite or Python-test reference. History shows that it entered through the former Next.js bridge shim and the same service operation remains exposed by `apps/api/app/routes/companies.py`, but there is no current evidence of intentional bridge retention. |
| `save_company_excel` | Intentionally Python-only legacy method | Defined in `desktop/bridge_api/companies.py`; no active Vite or Python-test reference. The active `export_company_excel` implementation explicitly describes `save_company_excel` as the old browser download flow. |
| `track_company_view` | Active Python-only method | Defined in `desktop/bridge_api/companies.py` and directly covered by the read/write-policy cases in `tests/test_bridge_write_policy.py`; no active Vite reference. |

## TypeScript-only methods

None. The generated inventory reports an empty `typescript_only` list.

## Duplicate declarations

None. The generated inventory reports an empty `typescript_duplicates` list.

## Decision

This inventory added, removed, renamed, generated, or changed no runtime method
or TypeScript declaration. It introduced no schema framework or dependency.
Any mismatch correction or other contract follow-up requires a separately
scoped issue and the applicable approval before implementation.
