# Company Chart Controls Design

## Goal

Make the company overview charts quieter and more flexible without obscuring
period, units, source state, or chart interpretation.

## Scope

- Render panel titles as `Historical Market Data` and `Financial Indicators`.
- Remove the always-visible source and ticker/methodology subtitles from the
  normal loaded chart panels. Loading, empty, stale, and error states retain
  their explicit state copy.
- Replace the Financial Indicators annual/quarterly segmented control with the
  existing compact select pattern used by Period.
- Replace the Market Data single View segmented control with a checkbox-backed
  metric selector for Price, Return, Dividend Yield, and Volume.

## Market Metric Selection

The selector may enable any number of metrics as long as their selected series
use no more than two units. Price uses BRL, Return and Dividend Yield share
percent, and Volume uses volume. A third distinct unit is disabled with a
concise explanation. Existing individual-series selection remains available,
so analysts can choose Close versus Adjusted Close and Price Return versus
Total Shareholder Return.

The chart receives selected series across enabled metrics. Series retain their
unit and are assigned to the two available axes by unit, preserving the
existing chart's truthful unit rendering. Defaults remain Adjusted Close for
Price, both return series for Return, TTM Dividend Yield for Dividend Yield,
and Trading Volume for Volume.

## Interaction and State

- At least one market metric remains enabled; an attempted deselection of the
  last one leaves Price selected.
- Metric choices, series selections, chart types, and existing chart options
  persist in the existing browser-local chart configuration.
- Market chart type resolves safely to a type compatible with all enabled
  metrics. The UI keeps the current type when valid and falls back to Line
  when it is not.
- Keyboard focus and native select semantics are preserved. The metric picker
  uses the existing checkbox picker pattern instead of a new dependency.

## Validation

- Unit-test selection sanitation, two-unit enforcement, and chart series
  construction.
- Update component tests for titles, absence of normal-state subtitles, and
  select controls.
- Run the targeted frontend test, TypeScript typecheck, and a Playwright visual
  check at normal desktop width.
