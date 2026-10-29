# Company Excel Mapping Native Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open each company’s Excel Mapping workspace in a separate native desktop window from the export card, removing Excel Mapping from Company sub-navigation.

**Architecture:** The React export card calls a typed bridge facade. The bridge validates the company id and delegates native-window creation to an opener registered by `desktop/app.py`; the opener reuses the active Vite URL with a window-mode route. React detects that mode and renders the existing mapping workspace without the main shell or Company navigation.

**Tech Stack:** React, TypeScript, React Router, Vitest, Vite, Python 3.11, pywebview, pytest.

## Global Constraints

- New Vite user-facing copy is English-only.
- The bridge facade remains the only frontend access path to `window.pywebview.api`.
- Do not alter workbook generation, mapping data, refresh behavior, or the database schema.
- Browser preview remains usable; native-window launch is desktop-only and reports an explicit local error.
- Preserve loading, error, empty, and partial-data states in the mapping workspace.
- Use minimal, analyst-grade controls and respect keyboard focus and reduced motion.

---

### Task 1: Register a testable native window opener in the desktop bridge

**Files:**
- Modify: `desktop/bridge_api/base.py`
- Modify: `desktop/app.py`
- Test: `tests/test_desktop_excel_mapping_window.py`

**Interfaces:**
- Produces: `BaseBridgeMixin.set_excel_mapping_window_opener(opener: Callable[[int], dict[str, object]]) -> None`.
- Produces: `CVMBridge.open_company_excel_mapping_window(params: dict | None) -> dict`.
- Consumes: application URL supplied by `desktop/app.py` after the Vite/static server is known.

- [ ] **Step 1: Write the failing bridge test**

```python
def test_open_company_excel_mapping_window_delegates_valid_cvm_id() -> None:
    bridge = CVMBridge()
    opened: list[int] = []
    bridge.set_excel_mapping_window_opener(lambda cd_cvm: opened.append(cd_cvm) or {"ok": True})

    assert bridge.open_company_excel_mapping_window({"cd_cvm": 9512}) == {"ok": True}
    assert opened == [9512]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_desktop_excel_mapping_window.py::test_open_company_excel_mapping_window_delegates_valid_cvm_id -q`

Expected: FAIL because the bridge does not expose `set_excel_mapping_window_opener`.

- [ ] **Step 3: Write the minimal bridge and desktop opener implementation**

```python
def set_excel_mapping_window_opener(self, opener):
    self._excel_mapping_window_opener = opener

def open_company_excel_mapping_window(self, params=None):
    cd_cvm = int((params or {}).get("cd_cvm") or 0)
    if cd_cvm <= 0:
        return {"ok": False, "error": "A valid CVM code is required."}
    if self._excel_mapping_window_opener is None:
        return {"ok": False, "error": "Excel Mapping windows are unavailable."}
    return self._excel_mapping_window_opener(cd_cvm)
```

In `desktop/app.py`, register an opener after `url` is resolved. It creates or focuses a pywebview window with URL `f"{url}?window=excel-mapping#/empresas/{cd_cvm}/model-mapping"`, a company-specific title, a bounded initial desktop size, and no extra server or database connection.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_desktop_excel_mapping_window.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add desktop/app.py desktop/bridge_api/base.py tests/test_desktop_excel_mapping_window.py
git commit -m "feat: open Excel mapping in native window"
```

### Task 2: Add the typed frontend launch contract and export-card affordance

**Files:**
- Modify: `apps/desktop-web/src/lib/bridge/types.ts`
- Modify: `apps/desktop-web/src/lib/api/companyDetail.ts` or add `apps/desktop-web/src/lib/api/companyWindows.ts`
- Modify: `apps/desktop-web/src/components/CompanyCommandBar.tsx`
- Modify: `apps/desktop-web/src/components/CompanyCommandBar.test.ts`
- Modify: `apps/desktop-web/src/lib/bridge/mock.ts`

**Interfaces:**
- Consumes: `BridgeApi.open_company_excel_mapping_window({ cd_cvm: number })`.
- Produces: `openCompanyExcelMappingWindow(cdCvm: number): Promise<{ mode: "desktop" | "browser"; result: { ok: boolean; error?: string | null } | null; reason?: string }`.
- Produces: an accessible button in `CompanyExportCard`, labelled `Open Excel Mapping in a separate window`.

- [ ] **Step 1: Write the failing frontend contract test**

```ts
it("keeps export separate while exposing the native Excel Mapping launcher", () => {
  expect(COMPANY_COMMAND_LABELS.excelMappingWindow).toBe(
    "Open Excel Mapping in a separate window",
  );
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix apps/desktop-web run test -- CompanyCommandBar.test.ts`

Expected: FAIL because `excelMappingWindow` is not defined.

- [ ] **Step 3: Write minimal typed facade and control**

```ts
export async function openCompanyExcelMappingWindow(cdCvm: number) {
  const mode = await whenBridgeReady();
  if (mode !== "desktop") return { mode: "browser" as const, result: null, reason: BROWSER_REASON };
  return { mode, result: await callBridge("open_company_excel_mapping_window", { cd_cvm: cdCvm }) };
}
```

Place a compact, focus-visible arrow button in the lower-right of `CompanyExportCard`. Its action calls the facade, shows an inline error only when the bridge rejects the request, and never changes the current Company route. Add the bridge signature and a browser/mock implementation so the type contract is complete.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix apps/desktop-web run test -- CompanyCommandBar.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop-web/src/lib/bridge/types.ts apps/desktop-web/src/lib/api/companyWindows.ts apps/desktop-web/src/components/CompanyCommandBar.tsx apps/desktop-web/src/components/CompanyCommandBar.test.ts apps/desktop-web/src/lib/bridge/mock.ts
git commit -m "feat: add Excel mapping window launcher"
```

### Task 3: Isolate window-mode rendering and remove the navigation tab

**Files:**
- Modify: `apps/desktop-web/src/App.tsx`
- Modify: `apps/desktop-web/src/components/shell/SubNav.tsx`
- Modify: `apps/desktop-web/src/routes/CompanyModelMappingPage.tsx`
- Create: `apps/desktop-web/src/lib/windowMode.ts`
- Create: `apps/desktop-web/src/lib/windowMode.test.ts`
- Create: `apps/desktop-web/src/components/shell/SubNav.test.ts`

**Interfaces:**
- Produces: `isExcelMappingWindow(): boolean`, true only for `?window=excel-mapping`.
- Consumes: existing route `/empresas/:cdCvm/model-mapping`.
- Produces: a shell-free mapping page when the window mode is active.

- [ ] **Step 1: Write the failing window-mode and navigation tests**

```ts
it("identifies the native Excel Mapping window query", () => {
  expect(isExcelMappingWindow("?window=excel-mapping")).toBe(true);
  expect(isExcelMappingWindow("")).toBe(false);
});

it("does not expose Excel Mapping as a Company sub-navigation tab", () => {
  expect(subNavFor("/empresas/9512", { cdCvm: "9512" }, null)).not.toContainEqual(
    expect.objectContaining({ label: "Excel Mapping" }),
  );
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix apps/desktop-web run test -- windowMode.test.ts SubNav.test.ts`

Expected: FAIL because no window-mode helper exists and the Company nav retains the mapping tab.

- [ ] **Step 3: Implement the focused window route**

```tsx
const isMappingWindow = isExcelMappingWindow(window.location.search);

return isMappingWindow ? (
  <HashRouter><CompanyModelMappingPage windowMode /></HashRouter>
) : (
  <HashRouter><AppShellWithPalette /></HashRouter>
);
```

Update `CompanyModelMappingPage` so `windowMode` removes the EntityHeader and CompanyCommandBar but retains the mapping page title, all mapping controls, loading/error/empty states, and export action. Remove the Excel Mapping item from `subNavFor` while preserving its route for bookmarks and the native window.

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm --prefix apps/desktop-web run test -- windowMode.test.ts SubNav.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop-web/src/App.tsx apps/desktop-web/src/components/shell/SubNav.tsx apps/desktop-web/src/routes/CompanyModelMappingPage.tsx apps/desktop-web/src/lib/windowMode.ts apps/desktop-web/src/lib/windowMode.test.ts apps/desktop-web/src/components/shell/SubNav.test.ts
git commit -m "feat: isolate Excel mapping window workspace"
```

### Task 4: Validate the end-to-end behavior

**Files:**
- Modify only if validation identifies a focused regression.

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: validation evidence only.

- [ ] **Step 1: Run targeted and Python regression tests**

Run:

```bash
pytest tests/test_desktop_excel_mapping_window.py tests/test_desktop_runtime_paths.py -q
npm --prefix apps/desktop-web run test -- CompanyCommandBar.test.ts windowMode.test.ts SubNav.test.ts
```

Expected: PASS.

- [ ] **Step 2: Run static validation**

Run:

```bash
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
```

Expected: exit code 0 for both.

- [ ] **Step 3: Perform visual and desktop runtime verification**

Use Playwright against browser preview to confirm the Company sub-navigation omits Excel Mapping, the export card exposes the labelled launcher, and `?window=excel-mapping#/empresas/9512/model-mapping` omits application chrome while preserving mapping content. Run desktop Dev mode and confirm one click creates/focuses a separately manageable native window.

- [ ] **Step 4: Record any validation-only corrective changes separately**

If validation requires a correction, amend the task-specific commit only after
rerunning the failing command. Do not stage unrelated work already present in
the working tree.
