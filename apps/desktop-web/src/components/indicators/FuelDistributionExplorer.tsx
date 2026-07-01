import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { StateBanner } from "@/components/feedback/StateBanner";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  fetchFuelDistributionDetail,
  fetchFuelDistributionProductYearSummary,
  fetchFuelDistributionStateMonthSeries,
} from "@/lib/api/energyKpis";
import type {
  FuelDistributionProductYearSummaryItem,
  FuelDistributionStateMonthSeriesItem,
} from "@/lib/bridge/types";

const STATE_MONTH_SOURCE = "anp_fuel_sales_state_month";
const DEFAULT_PRODUCT = "GASOLINA C";
const DEFAULT_STATE = "SÃO PAULO";

export function FuelDistributionExplorer({ bridgeReady }: { bridgeReady: boolean }) {
  const currentYear = new Date().getFullYear();
  const [product, setProduct] = useState(DEFAULT_PRODUCT);
  const [state, setState] = useState(DEFAULT_STATE);
  const [startYear, setStartYear] = useState(String(currentYear - 2));
  const [endYear, setEndYear] = useState(String(currentYear));
  const [selected, setSelected] = useState<FuelDistributionProductYearSummaryItem | null>(null);

  const normalizedProduct = product.trim().toUpperCase();
  const normalizedState = state.trim().toUpperCase();
  const parsedStartYear = parseYear(startYear);
  const parsedEndYear = parseYear(endYear);

  const summaryQuery = useQuery({
    queryKey: ["fuel-distribution-product-year", normalizedProduct, parsedStartYear, parsedEndYear],
    queryFn: () =>
      fetchFuelDistributionProductYearSummary({
        product: normalizedProduct || undefined,
        start_year: parsedStartYear ?? undefined,
        end_year: parsedEndYear ?? undefined,
        limit: 100,
      }),
    enabled: bridgeReady,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const summaryRows =
    summaryQuery.data?.mode === "desktop" ? summaryQuery.data.response.items ?? [] : [];

  useEffect(() => {
    if (!summaryRows.length) {
      setSelected(null);
      return;
    }
    const stillVisible = selected
      ? summaryRows.some(
          (row) =>
            row.source_dataset_id === selected.source_dataset_id &&
            row.product === selected.product &&
            row.year === selected.year &&
            row.unit === selected.unit,
        )
      : false;
    if (!stillVisible) setSelected(summaryRows[0]);
  }, [summaryRows, selected]);

  const seriesQuery = useQuery({
    queryKey: ["fuel-distribution-state-month", normalizedProduct, normalizedState, parsedStartYear, parsedEndYear],
    queryFn: () =>
      fetchFuelDistributionStateMonthSeries({
        source_dataset_id: STATE_MONTH_SOURCE,
        product: normalizedProduct,
        state: normalizedState || undefined,
        start_period: parsedStartYear ? `${parsedStartYear}-01` : undefined,
        end_period: parsedEndYear ? `${parsedEndYear}-12` : undefined,
        limit: 240,
      }),
    enabled: bridgeReady && normalizedProduct.length > 0,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const detailQuery = useQuery({
    queryKey: [
      "fuel-distribution-detail",
      selected?.source_dataset_id,
      selected?.product,
      selected?.year,
      normalizedState,
    ],
    queryFn: () =>
      fetchFuelDistributionDetail({
        source_dataset_id: selected?.source_dataset_id ?? "",
        product: selected?.product ?? "",
        year: selected?.year ?? currentYear,
        region_or_state: normalizedState || undefined,
        limit: 25,
        offset: 0,
      }),
    enabled: bridgeReady && !!selected,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const bridgeReason =
    summaryQuery.data?.mode === "browser"
      ? summaryQuery.data.reason
      : seriesQuery.data?.mode === "browser"
        ? seriesQuery.data.reason
        : detailQuery.data?.mode === "browser"
          ? detailQuery.data.reason
          : null;
  const seriesRows =
    seriesQuery.data?.mode === "desktop" ? seriesQuery.data.response.items ?? [] : [];
  const detail =
    detailQuery.data?.mode === "desktop" ? detailQuery.data.response : null;
  const totals = useMemo(() => summarize(summaryRows, seriesRows), [summaryRows, seriesRows]);

  if (!bridgeReady || summaryQuery.isLoading) {
    return <StateBanner variant="loading" title="Loading Fuel Distribution data..." />;
  }
  if (bridgeReason) {
    return <StateBanner variant="browser-only" message={bridgeReason} />;
  }
  if (summaryQuery.isError || seriesQuery.isError || detailQuery.isError) {
    const error = summaryQuery.error ?? seriesQuery.error ?? detailQuery.error;
    return (
      <StateBanner
        variant="error"
        title="Could not load Fuel Distribution data"
        message={error instanceof Error ? error.message : String(error)}
        onRetry={() => {
          void summaryQuery.refetch();
          void seriesQuery.refetch();
          void detailQuery.refetch();
        }}
      />
    );
  }

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-1">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-zinc-100">Fuel Distribution</h2>
            <p className="max-w-3xl text-sm text-zinc-400">
              ANP fuel sales read from compact SQLite marts first, with bounded
              Parquet detail only after product, source, and year are selected.
            </p>
          </div>
          <span className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-300">
            managed store
          </span>
        </div>
      </header>

      <section className="grid gap-3 rounded-md border border-zinc-800 bg-zinc-950/50 p-3 md:grid-cols-4">
        <label className="space-y-1 text-xs text-zinc-400">
          Product
          <Input value={product} onChange={(event) => setProduct(event.target.value)} />
        </label>
        <label className="space-y-1 text-xs text-zinc-400">
          State
          <Input value={state} onChange={(event) => setState(event.target.value)} />
        </label>
        <label className="space-y-1 text-xs text-zinc-400">
          Start year
          <Input mono value={startYear} onChange={(event) => setStartYear(event.target.value)} />
        </label>
        <label className="space-y-1 text-xs text-zinc-400">
          End year
          <Input mono value={endYear} onChange={(event) => setEndYear(event.target.value)} />
        </label>
      </section>

      <section className="grid gap-3 md:grid-cols-3">
        <MetricCard label="Summary rows" value={formatInteger(summaryRows.length)} />
        <MetricCard label="Trend rows" value={formatInteger(seriesRows.length)} />
        <MetricCard label="Selected total" value={formatMeasure(totals.summaryTotal, selected?.unit ?? "m3")} />
      </section>

      {summaryRows.length === 0 ? (
        <StateBanner
          variant="empty"
          title="No Fuel Distribution mart rows"
          message="Change the filters or run the ANP Fuel Distribution importer to rebuild the local managed store."
        />
      ) : (
        <section className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <Panel title="Product / Year Summary" subtitle="SQLite mart">
            <div className="max-h-[360px] overflow-auto rounded border border-zinc-800">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-zinc-900">
                  <tr className="border-b border-zinc-800 text-left text-[10px] uppercase tracking-wide text-zinc-500">
                    <Th>Product</Th>
                    <Th>Source</Th>
                    <Th align="right">Year</Th>
                    <Th align="right">Value</Th>
                    <Th align="right">Rows</Th>
                  </tr>
                </thead>
                <tbody>
                  {summaryRows.map((row) => {
                    const active =
                      selected?.source_dataset_id === row.source_dataset_id &&
                      selected?.product === row.product &&
                      selected?.year === row.year &&
                      selected?.unit === row.unit;
                    return (
                      <tr
                        key={`${row.source_dataset_id}-${row.product}-${row.year}-${row.unit}`}
                        className={`border-b border-zinc-800/60 hover:bg-zinc-800/40 ${
                          active ? "bg-amber-500/10" : "bg-zinc-950/30"
                        }`}
                      >
                        <Td strong>{row.product}</Td>
                        <Td muted>{compactSource(row.source_dataset_id)}</Td>
                        <Td align="right" mono>{row.year}</Td>
                        <Td align="right" mono>{formatMeasure(row.total_value, row.unit)}</Td>
                        <Td align="right">
                          <Button size="xs" variant={active ? "primary" : "secondary"} onClick={() => setSelected(row)}>
                            {formatInteger(row.source_row_count)}
                          </Button>
                        </Td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="State / Month Trend" subtitle={`${normalizedState || "All states"} · ${STATE_MONTH_SOURCE}`}>
            {seriesRows.length === 0 ? (
              <StateBanner
                variant="empty"
                title="No state/month rows"
                message="State/month trends are available for monthly ANP sources. Try GASOLINA C and SÃO PAULO."
                size="dense"
              />
            ) : (
              <div className="max-h-[360px] overflow-auto rounded border border-zinc-800">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-zinc-900">
                    <tr className="border-b border-zinc-800 text-left text-[10px] uppercase tracking-wide text-zinc-500">
                      <Th>Period</Th>
                      <Th>State</Th>
                      <Th align="right">Value</Th>
                      <Th align="right">Rows</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {seriesRows.map((row) => (
                      <tr
                        key={`${row.source_dataset_id}-${row.product}-${row.reference_period}-${row.state}-${row.unit}`}
                        className="border-b border-zinc-800/60 bg-zinc-950/30 hover:bg-zinc-800/40"
                      >
                        <Td mono>{row.reference_period}</Td>
                        <Td>{row.state}</Td>
                        <Td align="right" mono>{formatMeasure(row.total_value, row.unit)}</Td>
                        <Td align="right" mono>{formatInteger(row.source_row_count)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </section>
      )}

      <Panel
        title="Bounded Detail Preview"
        subtitle={selected ? `${selected.source_dataset_id} · ${selected.product} · ${selected.year}` : "Select a summary row"}
      >
        {!selected ? (
          <StateBanner variant="empty" title="No selected row" message="Select a summary row to read bounded Parquet detail." size="dense" />
        ) : detailQuery.isFetching && !detail ? (
          <StateBanner variant="loading" title="Loading detail preview..." size="dense" />
        ) : !detail || detail.rows.length === 0 ? (
          <StateBanner variant="empty" title="No detail rows" message="No matching detail rows were found for the selected source/product/year and state filter." size="dense" />
        ) : (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-zinc-500">
              <span>
                Showing {formatInteger(detail.count)} of {formatInteger(detail.total_matching_rows)} rows
                {detail.truncated ? " · truncated" : ""}
              </span>
              <span className="font-mono">{detail.source}</span>
            </div>
            <div className="max-h-[280px] overflow-auto rounded border border-zinc-800">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-zinc-900">
                  <tr className="border-b border-zinc-800 text-left text-[10px] uppercase tracking-wide text-zinc-500">
                    <Th>Period</Th>
                    <Th>Region</Th>
                    <Th>State</Th>
                    <Th>Municipality</Th>
                    <Th align="right">Value</Th>
                  </tr>
                </thead>
                <tbody>
                  {detail.rows.map((row, index) => (
                    <tr key={index} className="border-b border-zinc-800/60 bg-zinc-950/30 hover:bg-zinc-800/40">
                      <Td mono>{cell(row.reference_period)}</Td>
                      <Td>{cell(row.region)}</Td>
                      <Td>{cell(row.state)}</Td>
                      <Td>{cell(row.municipality)}</Td>
                      <Td align="right" mono>{formatMeasure(asNumber(row.value), String(row.unit ?? selected.unit))}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}

function Panel({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <section className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-zinc-200">{title}</h3>
        <span className="truncate text-[11px] text-zinc-500">{subtitle}</span>
      </div>
      {children}
    </section>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3">
      <div className="text-[11px] uppercase tracking-wide text-zinc-500">{label}</div>
      <div className="mt-1 font-mono text-lg font-semibold tabular-nums text-zinc-100">{value}</div>
    </div>
  );
}

function Th({ children, align = "left" }: { children: ReactNode; align?: "left" | "right" }) {
  return <th className={`px-3 py-2 font-semibold ${align === "right" ? "text-right" : "text-left"}`}>{children}</th>;
}

function Td({
  children,
  align = "left",
  mono = false,
  muted = false,
  strong = false,
}: {
  children: ReactNode;
  align?: "left" | "right";
  mono?: boolean;
  muted?: boolean;
  strong?: boolean;
}) {
  const color = muted ? "text-zinc-500" : strong ? "text-zinc-200" : "text-zinc-300";
  return (
    <td className={`px-3 py-2 ${align === "right" ? "text-right" : "text-left"} ${mono ? "font-mono tabular-nums" : ""} ${color}`}>
      {children}
    </td>
  );
}

function summarize(summaryRows: FuelDistributionProductYearSummaryItem[], seriesRows: FuelDistributionStateMonthSeriesItem[]) {
  return {
    summaryTotal: summaryRows.reduce((acc, row) => acc + row.total_value, 0),
    seriesTotal: seriesRows.reduce((acc, row) => acc + row.total_value, 0),
  };
}

function parseYear(value: string): number | null {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1900 || parsed > 2100) return null;
  return parsed;
}

function formatMeasure(value: number | null | undefined, unit: string): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value.toLocaleString("en-US", { maximumFractionDigits: value >= 1000 ? 0 : 2 })} ${unit}`;
}

function formatInteger(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function compactSource(value: string): string {
  return value.replace(/^anp_/, "").replace(/_/g, " ");
}

function cell(value: unknown): string {
  if (value == null || value === "") return "—";
  return String(value);
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
