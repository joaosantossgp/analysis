# Companies Directory Controls Design

## Goal

Reduce redundant controls in the Companies directory and let analysts sort the complete filtered directory from its table headers.

## Approved design

- Remove the visible `Search` and `Sector (GICS)` labels.
- Keep the existing search placeholder and add an in-field search icon with an accessible label.
- Remove the market-cap summary banner, including its ranking, source, and snapshot copy.
- Make every directory column header a button. Clicking an inactive header sorts ascending; clicking it again reverses direction. The active header alone shows an up/down arrow and exposes its state to assistive technology.
- Persist `sort` and `direction` in the route query string, reset pagination to page 1 when either changes, and apply the sort before pagination in every desktop directory data path.

## Data and behavior

The bridge accepts only an allowlisted sort key and `asc`/`desc`; invalid values fall back to the existing default market-cap descending order. Text columns use case-insensitive alphabetic order. Numeric columns use numeric order. Missing values are stable and placed last.

## Scope

Only the active Vite Companies screen and its local desktop read path change. No schema, source data, refresh, or external data-provider behavior changes.
