# Analyst Workspace (Home) Validation Checklist

> **Historical checklist (superseded 2026-11-16).** The earlier Home layout below
> predates News retirement and the two-widget recommended layout. It is not a
> current release gate. Use the [current Home contract](../PRODUCT.md#primary-navigation-and-home)
> and [release validation requirements](../build-release.md), with the
> [company-focused UI evidence](../governance/2026-11-12-company-focus-ui.md) for the
> delivered transition. The original scenarios are retained as historical context.

This checklist defines the manual validation scenarios required before release to verify layout integrity, persistence safety, and data export correctness.

---

## 1. First-Run Guided State UX

- [ ] **Empty State Clean Check:**
  - Clear localStorage keys `cvm:home:workspace:items:v4` and `cvm:home:workspace:config:v4` in developer console.
  - Refresh the app to the home page `/`.
  - Confirm the page renders a guided workspace initial setup.
  - Verify that the layout does not look blank, broken, or contain raw JSON text.
  - Verify two CTA buttons are visible: "Load Recommended Layout" and "Choose Widgets Manually".
- [ ] **Recommended Layout Initialization:**
  - Click **Load Recommended Layout**.
  - Confirm that 5 widgets spawn: Database Monitor, Watchlist, Market Price Sparkline, Priority Queue, and Top News Feed.
  - Confirm they arrange in a balanced columns layout without overlapping.
  - Refresh the page and confirm that the recommended layout persists.
- [ ] **Manual Setup Action:**
  - Clear localStorage again and refresh.
  - Click **Choose Widgets Manually**.
  - Confirm that Edit Mode is enabled (orange warning label active) and the widgets drawer slide-out menu is visible.

---

## 2. Layout Hardening & Snapping

- [ ] **Drag-Move Snapping:**
  - Enter Edit Mode.
  - Click and hold a card's header, then drag it.
  - Confirm that a dashed orange snap preview highlight displays under the card.
  - Drop the card and check that it snaps cleanly.
  - Refresh the page and verify the updated coordinates persist.
- [ ] **Width Snapping:**
  - Drag the right edge of a widget card in Edit Mode.
  - Verify it snaps to column widths of 1, 2, or 3 columns only.
  - Verify it cannot be resized wider than 3 columns or narrower than 1.
- [ ] **Height Snapping:**
  - Drag the bottom edge of a widget card in Edit Mode.
  - Verify it snaps to vertical increments of rows.
  - Verify it cannot be resized shorter than 2 rows or taller than 6 rows.
- [ ] **Collisions & Push-Down:**
  - Drag a widget on top of another widget.
  - Verify that the lower-priority widget gets pushed down smoothly.
  - Confirm that no overlapping cards are created on reloading the page.

---

## 3. Storage Failure Recovery

- [ ] **Malformed localStorage JSON:**
  - Open Developer Console $\rightarrow$ Application $\rightarrow$ Local Storage.
  - Set the key `cvm:home:workspace:items:v4` to `invalid_json_string`.
  - Refresh the home page.
  - Confirm the page does not crash (no white screen) and recovers to the initial guided setup.
- [ ] **Unknown Card IDs:**
  - Manually append an invalid item structure to localStorage items array:
    `{"id": "unknown-legacy-card", "x": 0, "y": 0, "w": 2, "h": 2}`
  - Refresh the home page.
  - Confirm the workspace ignores this widget, does not render an empty error block, and preserves all other valid cards.
- [ ] **Clamping Coordinates:**
  - Set the coordinates of a widget card in localStorage to overflow boundaries:
    `{"id": "market-price", "x": 10, "y": 20, "w": 5, "h": 10}`
  - Refresh the home page.
  - Verify that the card's width clamps to 3, height clamps to 6, and x-coordinate snaps back inside grid boundaries.

---

## 4. Centralized CSV Exporter

- [ ] **Accent Integrity (Excel Compat):**
  - Configure the Watchlist with a Brazilian company (e.g. `PETROBRAS` or `VALE`).
  - Maximize the card into Focus Mode.
  - Click the **⬇ CSV** action.
  - Open the downloaded `.csv` file in Microsoft Excel or LibreOffice.
  - Verify that Portuguese accents (e.g., `Petróleo`, `Mineração`, `Composição`) display correctly without encoding corruption.
- [ ] **Filename Sanitization:**
  - Configure a market price watch card.
  - Trigger a CSV download.
  - Confirm the filename is sanitized (no traversal characters like `..` or invalid characters like `* ? : / \`).
- [ ] **Empty Exports Guard:**
  - Try to export an empty Watchlist.
  - Verify that the export button is either hidden or operates as a safe, clear no-op.
