# Company Update: Financials and All Market Tickers

## Objective

Make the Company Workspace `Update data` action refresh both the company's
official CVM financial data and the locally cached Yahoo Finance market history
for every resolved B3 ticker of that company.

## Scope

- The existing CVM refresh remains an explicit, asynchronous company refresh
  job with its current range and progress behavior.
- A new bridge market-refresh mode resolves the full ticker candidate set using
  `resolve_company_tickers` and refreshes each ticker sequentially.
- The market result reports each ticker independently, so one unavailable or
  failed Yahoo ticker cannot discard data or obscure successful ticker updates.
- The Company Command Bar presents one action and concise combined feedback.
- On completion, cached market status/history queries are invalidated so the
  Historical market data panel reflects the refreshed local cache.
- The on-demand settings popover opened from the Download history card keeps
  two local, analyst-owned toggles: `CVM financial data` and `Market data`.
  Both default to selected and control the sources used by `Update data`.
- The popover explicitly labels `Download history` as CVM-only. Market history
  continues to request its complete provider history during a market update;
  no market date-range selector is added.

## Non-goals

- Do not put Yahoo Finance inside the CVM refresh worker or its financial-data
  progress model.
- Do not update tickers concurrently; sequential calls reduce provider-rate
  pressure and make partial results deterministic.
- Do not alter the existing standalone Historical market data update action.
- Do not hide a source failure: CVM dispatch and market results remain
  independently visible in the combined notice.
- Do not refresh market-cap data from this or any other update flow. Existing
  local market-cap snapshots remain readable offline, but no bridge action,
  refresh job, or Update Base fallback may fetch a replacement snapshot.

## Data flow

1. The user clicks `Update data` in the Company Command Bar.
2. The frontend dispatches the existing CVM incremental refresh and requests
   the new market `all_tickers` refresh through the desktop bridge.
3. The bridge resolves candidate tickers, refreshes each one sequentially, and
   returns a per-ticker summary plus aggregate successes/failures.
4. The frontend invalidates the company financial queries and every
   `market-history` / `market-history-status` query for that company.
5. The Command Bar shows concise source-aware feedback; financial job progress
   continues to be polled through the existing status query.
6. `Update data` dispatches only the selected sources. If neither source is
   selected, the action is disabled with an explanatory accessibility label.

## Failure behavior

- A CVM dispatch failure does not prevent an attempted market refresh, and a
  market refresh failure does not cancel a successfully queued CVM job.
- A ticker error leaves its prior local market cache untouched, following the
  existing idempotent market-history service behavior.
- If no ticker resolves, the market aggregate succeeds with zero attempts and
  a visible explanatory warning rather than pretending a market update ran.

## Validation

- Python tests cover all-ticker resolution, sequential calls, partial failure,
  and preservation of previous local rows.
- Frontend tests cover combined result formatting and market query invalidation.
- Typecheck, targeted tests, build, and Playwright verification cover the
  Company Command Bar and Historical market data panel.
