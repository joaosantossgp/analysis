# Company Excel Mapping native window

## Objective

Move Excel Mapping out of the Company workspace sub-navigation and expose it as
an independent native desktop window opened from the company export card.

## User flow

1. The Company workspace keeps Overview, Financial Statements, and Coverage
   Status in its sub-navigation.
2. The export card includes a compact lower-right launch affordance with an
   accessible label for opening Excel Mapping.
3. Selecting the affordance asks the desktop bridge to open a native window
   for the current CVM company id.
4. The new window loads the existing Excel Mapping workspace for that company,
   without the global shell or Company sub-navigation.
5. The analyst can minimise, maximise, resize, switch to, and close the
   mapping window using normal Windows controls. Closing it leaves the Company
   workspace unchanged.

## Architecture

- The desktop application owns native window creation through pywebview.
- The existing Vite route remains the data/rendering source for Excel Mapping.
- A dedicated window-mode entry condition renders the mapping route without
  the main TerminalShell, avoiding a second full application chrome.
- The frontend only calls the typed bridge facade; it does not call
  `window.pywebview.api` directly.
- Browser preview remains functional: the launch affordance is disabled with a
  clear reason because native secondary windows are desktop-only.

## State and error handling

- Opening the window is non-destructive and does not alter the parent route.
- Bridge failures surface next to the launch control through the existing
  feedback pattern.
- The Mapping page preserves its current loading, error, empty, and data
  states in the separate window.
- Repeated launch requests focus the company mapping window where practical;
  otherwise they must not corrupt the parent or local database state.

## Validation

- Add a frontend regression test for the launch affordance and for removal of
  Excel Mapping from Company sub-navigation.
- Add a focused Python test for the bridge request/window URL construction,
  avoiding a real GUI dependency.
- Run the relevant tests, desktop-web typecheck and build.
- Verify the normal Company workspace and mapping-window route in browser
  preview; manually verify the native window in desktop Dev mode.

## Scope boundary

This change changes presentation and navigation only. It does not change Excel
workbook generation, mapping data, refresh behavior, or database schema.
