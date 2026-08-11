# Disable Market-Cap Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent every application flow from fetching or replacing the market-cap snapshot while preserving offline reads of an existing snapshot.

**Architecture:** Remove the market-cap stage from `RefreshService.execute`, remove the Update Base bootstrap fallback, and remove the exposed desktop bridge fetch action. Keep `MarketCapService.read_snapshot` and snapshot import/read contracts unchanged.

**Tech Stack:** Python 3.11, pytest, desktop pywebview bridge, TypeScript bridge contract.

## Global Constraints

- Existing local market-cap snapshots remain readable offline.
- No CVM financial refresh, market-history refresh, Update Base flow, or bridge method may invoke Yahoo Finance market-cap fetching.
- Do not delete user snapshots or alter their schema.
- New desktop UI strings remain English-only.

---

### Task 1: Remove automatic market-cap execution

**Files:**
- Modify: `src/refresh/service.py:432-567`
- Modify: `tests/test_refresh_service.py:250-388`

**Interfaces:**
- Consumes: `RefreshService.execute(request, stage_callback, persist_refresh_status)`.
- Produces: `RefreshResult.market_cap_result is None` and no `market_cap` progress update for every refresh request.

- [ ] **Step 1: Write the failing regression test**

```python
def test_execute_never_refreshes_market_cap(tmp_path, monkeypatch):
    service = _make_service(tmp_path)
    from src.companies.market_cap import MarketCapService
    monkeypatch.setattr(
        MarketCapService,
        "fetch_from_yahoo_finance",
        lambda *_args, **_kwargs: pytest.fail("market-cap refresh must not run"),
    )
    stages_seen = []
    result = service.execute(_refresh_request(), stage_callback=lambda update: stages_seen.append(update.stage))
    assert "market_cap" not in stages_seen
    assert result.market_cap_result is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_refresh_service.py -k never_refreshes_market_cap -q`

Expected: FAIL because `RefreshService.execute` calls `fetch_from_yahoo_finance`.

- [ ] **Step 3: Remove the market-cap stage and obsolete tests**

```python
def execute(
    self,
    request: RefreshRequest,
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
    stage_callback: Callable[[RefreshProgressUpdate], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    persist_refresh_status: bool = True,
) -> RefreshResult:
    market_cap_result = None
    planned_companies, company_year_overrides, planning_stats = self.build_company_year_plan(request)
    # Continue directly with financial-refresh planning and execution.
```

Remove the former success/fallback/blocked stage assertions; their behavior is no longer part of refresh execution.

- [ ] **Step 4: Run the targeted tests**

Run: `pytest tests/test_refresh_service.py -q`

Expected: PASS.

### Task 2: Remove bridge-level market-cap fetch triggers

**Files:**
- Modify: `desktop/bridge_api/refresh.py:472-481, 570-615`
- Modify: `apps/desktop-web/src/lib/bridge/types.ts:1594-1600`
- Modify: `apps/desktop-web/src/lib/bridge/mock.ts:2716-2734`

**Interfaces:**
- Consumes: `start_data_update` when company universe data is unavailable.
- Produces: a blocked response from `start_data_update` without an inline market-cap fetch; no `fetch_latest_market_cap` bridge method.

- [ ] **Step 1: Write the failing bridge regression test**

```python
def test_start_data_update_does_not_fetch_market_cap_when_universe_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MarketCapService, "fetch_from_yahoo_finance", forbidden_fetch)
    result = bridge.start_data_update({"mode": "missing"})
    assert result["status"] == "blocked"
    assert forbidden_fetch.calls == 0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_bridge_refresh.py -k market_cap -q`

Expected: FAIL while the fallback still invokes `fetch_from_yahoo_finance`.

- [ ] **Step 3: Remove all exposed and fallback fetch paths**

```python
except CompanyUniverseUnavailableError as exc:
    return self._sanitize_for_json({
        "status": "blocked",
        "job_id": None,
        "message": str(exc),
        "status_reason_code": "company_universe_unavailable",
        "status_reason_message": str(exc),
    })
```

Delete `fetch_latest_market_cap` from the bridge mixin, TypeScript `BridgeApi`, and mock bridge. Retain status/list/import operations for offline snapshot use.

- [ ] **Step 4: Run bridge and frontend type validation**

Run: `pytest tests/test_desktop_runtime_paths.py -q; npm --prefix apps/desktop-web run typecheck`

Expected: PASS.

### Task 3: Verify update flows and document the retained behavior

**Files:**
- Modify: `docs/dev-runtime-and-data-paths.md` only if it describes an automatic market-cap fetch.
- Verify: `apps/desktop-web/src/components/CompanyCommandBar.tsx`
- Verify: `apps/desktop-web/src/components/MarketHistoryPanel.tsx`

**Interfaces:**
- Consumes: the existing company `Update data` actions.
- Produces: financial refresh and per-ticker market-history refresh remain available; market-cap remains local-snapshot-only.

- [ ] **Step 1: Update active documentation only when it claims an automatic refresh**

```markdown
Market-cap data is read from an existing local snapshot. Runtime update flows do not fetch or replace it.
```

- [ ] **Step 2: Run complete validation**

Run: `pytest tests/test_refresh_service.py tests/test_desktop_runtime_paths.py -q; npm --prefix apps/desktop-web run test -- CompanyCommandBar.test.ts; npm --prefix apps/desktop-web run typecheck; npm --prefix apps/desktop-web run build`

Expected: PASS.


- [ ] **Step 3: Visually verify the company update flow**

Run the Vite mock app, open `#/empresas/14673` with Playwright, and confirm `Update data` remains available without a market-cap progress stage or notice.
