import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/surface/Panel";
import { StateBanner } from "@/components/feedback/StateBanner";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import { fetchDataCoverage, setCompanyIgnored } from "@/lib/api/dataCoverage";
import {
  fetchRefreshJob,
  isActiveRefreshJob,
  isTerminalRefreshJob,
  startBaseRefresh,
} from "@/lib/api/updateBase";
import type {
  DataCoverageFilterId,
  DataCoverageResponse,
  DataCoverageRow,
  DataCoverageStatus,
} from "@/lib/bridge/types";

type FilterDef = {
  id: DataCoverageFilterId;
  label: string;
  predicate: (row: DataCoverageRow) => boolean;
};

const FILTERS: FilterDef[] = [
  // All non-ignored filters hide rows marked as ignored — the operator
  // explicitly removed them from the actionable view. Switch to "Ignored"
  // to inspect or restore them.
  { id: "all", label: "All Issues", predicate: (r) => !r.ignored && r.status !== "complete" },
  { id: "no_financial", label: "No Financial Data", predicate: (r) => !r.ignored && !r.has_dfp && !r.has_itr },
  { id: "no_dfp", label: "No DFP", predicate: (r) => !r.ignored && !r.has_dfp },
  { id: "no_itr", label: "No ITR", predicate: (r) => !r.ignored && !r.has_itr },
  { id: "stale", label: "Stale Data", predicate: (r) => !r.ignored && r.is_stale },
  { id: "failed", label: "Last Update Failed", predicate: (r) => !r.ignored && r.update_failed },
  { id: "ticker_unmapped", label: "Ticker Unmapped", predicate: (r) => !r.ignored && !r.ticker_mapped },
  { id: "no_registry", label: "Missing Registry", predicate: (r) => !r.ignored && !r.has_registry },
  { id: "ignored", label: "Ignored", predicate: (r) => r.ignored },
];

const STATUS_LABEL: Record<DataCoverageStatus, string> = {
  complete: "Complete",
  partial: "Partial",
  no_financial: "No Data",
  failed: "Failed",
  unmapped: "Unmapped",
  ignored: "Ignored",
};

const STATUS_TONE: Record<DataCoverageStatus, { bg: string; fg: string; border: string }> = {
  complete: { bg: "rgba(34,197,94,0.10)", fg: "var(--color-success, #4ade80)", border: "rgba(34,197,94,0.30)" },
  partial: { bg: "rgba(234,179,8,0.10)", fg: "var(--color-warning, #facc15)", border: "rgba(234,179,8,0.30)" },
  no_financial: { bg: "rgba(148,163,184,0.10)", fg: "var(--color-text-secondary)", border: "rgba(148,163,184,0.30)" },
  failed: { bg: "rgba(239,68,68,0.10)", fg: "var(--color-danger, #f87171)", border: "rgba(239,68,68,0.30)" },
  unmapped: { bg: "rgba(148,163,184,0.10)", fg: "var(--color-text-secondary)", border: "rgba(148,163,184,0.30)" },
  ignored: { bg: "rgba(82,82,91,0.20)", fg: "var(--color-text-tertiary)", border: "rgba(82,82,91,0.40)" },
};

const VIRTUAL_ROW_HEIGHT = 56;
const VIRTUAL_OVERSCAN = 8;
const BULK_CONFIRM_THRESHOLD = 10;
const TABLE_COLUMN_COUNT = 10;

const DATA_OPERATION_QUERY_KEYS: Array<readonly unknown[]> = [
  ["data-coverage"],
  ["base-health"],
  ["db-diagnostics"],
  ["companies"],
  ["company-filters"],
  ["company-refresh-status"],
  ["refresh-jobs"],
  ["app-status"],
];

function invalidateDataOperationQueries(queryClient: QueryClient) {
  for (const queryKey of DATA_OPERATION_QUERY_KEYS) {
    void queryClient.invalidateQueries({ queryKey });
  }
}

export function DataCoveragePage() {
  const queryClient = useQueryClient();
  const [bridgeReady, setBridgeReady] = useState(false);
  const [filter, setFilter] = useState<DataCoverageFilterId>("all");
  const [search, setSearch] = useState("");
  const [retryingCvm, setRetryingCvm] = useState<number | null>(null);
  const [activeRetryJobId, setActiveRetryJobId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkRunning, setBulkRunning] = useState<"ignore" | "restore" | null>(null);
  const [bulkError, setBulkError] = useState<string | null>(null);
  const invalidatedRetryJobRef = useRef<string | null>(null);

  // Reset selection when the visible row set changes.
  useEffect(() => {
    setSelected(new Set());
  }, [filter, search]);

  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then(() => {
      if (!cancelled) setBridgeReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const coverageQuery = useQuery({
    queryKey: ["data-coverage"],
    queryFn: fetchDataCoverage,
    enabled: bridgeReady,
    staleTime: 30_000,
  });

  const retryMutation = useMutation({
    mutationFn: async (cdCvm: number) => {
      setRetryingCvm(cdCvm);
      return startBaseRefresh({
        mode: "missing",
        limit: 1,
        startYear: 2010,
        endYear: new Date().getFullYear() - 1,
        cdCvm,
      });
    },
    onSuccess: (result) => {
      invalidatedRetryJobRef.current = null;
      if (result.job_id) {
        setActiveRetryJobId(result.job_id);
      } else {
        invalidateDataOperationQueries(queryClient);
      }
    },
    onSettled: () => {
      setRetryingCvm(null);
      invalidateDataOperationQueries(queryClient);
    },
  });

  const retryJobQuery = useQuery({
    queryKey: ["refresh-job", activeRetryJobId],
    queryFn: () => fetchRefreshJob(activeRetryJobId ?? ""),
    enabled: bridgeReady && Boolean(activeRetryJobId),
    refetchInterval: (query) => {
      const job = query.state.data?.mode === "desktop" ? query.state.data.job : null;
      return isActiveRefreshJob(job) ? 2_000 : false;
    },
  });

  const activeRetryJob =
    retryJobQuery.data?.mode === "desktop" ? retryJobQuery.data.job : null;

  useEffect(() => {
    if (!activeRetryJobId || !activeRetryJob || !isTerminalRefreshJob(activeRetryJob)) {
      return;
    }
    if (invalidatedRetryJobRef.current === activeRetryJobId) return;
    invalidatedRetryJobRef.current = activeRetryJobId;
    invalidateDataOperationQueries(queryClient);
    setActiveRetryJobId(null);
  }, [activeRetryJob, activeRetryJobId, queryClient]);

  const ignoreMutation = useMutation({
    mutationFn: async (args: { row: DataCoverageRow; ignored: boolean }) =>
      setCompanyIgnored({
        cdCvm: args.row.cd_cvm,
        ignored: args.ignored,
        companyName: args.row.company_name,
      }),
    onSettled: () => {
      invalidateDataOperationQueries(queryClient);
    },
  });

  const browserReason =
    coverageQuery.data?.mode === "browser" ? coverageQuery.data.reason : null;
  const data: DataCoverageResponse | null =
    coverageQuery.data?.mode === "desktop" ? coverageQuery.data.data : null;

  const filteredRows = useMemo(() => {
    if (!data) return [];
    const pred = FILTERS.find((f) => f.id === filter)?.predicate
      ?? (() => true);
    const q = search.trim().toLowerCase();
    return data.rows.filter((r) => {
      if (!pred(r)) return false;
      if (!q) return true;
      return (
        r.company_name.toLowerCase().includes(q)
        || String(r.cd_cvm).includes(q)
        || (r.ticker ?? "").toLowerCase().includes(q)
      );
    });
  }, [data, filter, search]);

  const filteredIds = useMemo(
    () => new Set(filteredRows.map((row) => row.cd_cvm)),
    [filteredRows],
  );

  useEffect(() => {
    setSelected((prev) => {
      if (prev.size === 0) return prev;
      let changed = false;
      const next = new Set<number>();
      for (const cdCvm of prev) {
        if (filteredIds.has(cdCvm)) next.add(cdCvm);
        else changed = true;
      }
      return changed ? next : prev;
    });
  }, [filteredIds]);

  async function runBulkIgnore(targetIgnored: boolean) {
    const targets = filteredRows.filter(
      (r) => selected.has(r.cd_cvm) && r.ignored !== targetIgnored,
    );
    if (targets.length === 0) return;
    if (
      targetIgnored
      && targets.length >= BULK_CONFIRM_THRESHOLD
      && !window.confirm(
        `Ignore ${targets.length} selected companies? They will be removed from actionable filters but can be restored under the Ignored filter.`,
      )
    ) {
      return;
    }
    setBulkRunning(targetIgnored ? "ignore" : "restore");
    setBulkError(null);
    try {
      // Sequential to avoid hammering the SQLite write lock; selection
      // sizes are small (UI shows max PAGE_SIZE rows at a time).
      for (const row of targets) {
        await setCompanyIgnored({
          cdCvm: row.cd_cvm,
          ignored: targetIgnored,
          companyName: row.company_name,
        });
      }
      setSelected(new Set());
    } catch (exc) {
      setBulkError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setBulkRunning(null);
      invalidateDataOperationQueries(queryClient);
    }
  }

  return (
    <section className="space-y-6">
      <PageHeader
        title="Data Coverage"
        subtitle="Companies with missing, incomplete, stale, or failed data."
        actions={
          <Link
            to="/settings/updates"
            style={{
              color: "var(--color-text-secondary)",
              fontSize: "var(--text-xs)",
              textDecoration: "underline",
            }}
          >
            ← Database Updates
          </Link>
        }
      />

      {browserReason ? <StateBanner variant="browser-only" message={browserReason} /> : null}

      {coverageQuery.isLoading || !bridgeReady ? (
        <StateBanner variant="loading" title="Loading coverage…" />
      ) : null}

      {coverageQuery.isError ? (
        <StateBanner
          variant="error"
          title="Failed to load coverage"
          message={
            coverageQuery.error instanceof Error
              ? coverageQuery.error.message
              : String(coverageQuery.error)
          }
          onRetry={() => { void coverageQuery.refetch(); }}
        />
      ) : null}

      {data ? <SummaryCards data={data} /> : null}

      {data ? (
        <Panel
          title="Filters"
          dense
        >
          <FilterChips
            data={data}
            current={filter}
            onChange={setFilter}
          />
          <div style={{ marginTop: 12 }}>
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name, CVM, or ticker…"
              style={{
                width: "100%",
                background: "var(--color-surface-1)",
                border: "1px solid var(--color-border-subtle)",
                borderRadius: "var(--radius-sm)",
                color: "var(--color-text-primary)",
                fontSize: "var(--text-sm)",
                padding: "8px 10px",
              }}
            />
          </div>
        </Panel>
      ) : null}

      {data ? (
        filteredRows.length === 0 ? (
          <StateBanner
            variant="empty"
            title="No issues for this filter"
            message="All companies in the selected universe have usable data for this criterion."
          />
        ) : (
          <>
            <BulkActionsBar
              selectedCount={selected.size}
              bulkRunning={bulkRunning}
              onIgnore={() => runBulkIgnore(true)}
              onRestore={() => runBulkIgnore(false)}
              onClear={() => setSelected(new Set())}
            />
            <CoverageTable
              rows={filteredRows}
              onRetry={(cdCvm) => retryMutation.mutate(cdCvm)}
              onToggleIgnored={(row) =>
                ignoreMutation.mutate({ row, ignored: !row.ignored })
              }
              retryingCvm={retryingCvm}
              ignoringCvm={
                ignoreMutation.isPending && ignoreMutation.variables
                  ? ignoreMutation.variables.row.cd_cvm
                  : null
              }
              disabled={retryMutation.isPending || bulkRunning != null}
              selected={selected}
              onToggleSelected={(cdCvm) =>
                setSelected((prev) => {
                  const next = new Set(prev);
                  if (next.has(cdCvm)) next.delete(cdCvm);
                  else next.add(cdCvm);
                  return next;
                })
              }
              onToggleSelectAll={(allSelected) =>
                setSelected((prev) => {
                  const next = new Set(prev);
                  if (allSelected) for (const r of filteredRows) next.delete(r.cd_cvm);
                  else for (const r of filteredRows) next.add(r.cd_cvm);
                  return next;
                })
              }
            />
            <p style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-xs)", textAlign: "right" }}>
              {filteredRows.length.toLocaleString("en-US")} compan{filteredRows.length === 1 ? "y" : "ies"}
            </p>
          </>
        )
      ) : null}

      {retryMutation.isError ? (
        <StateBanner
          variant="error"
          title="Could not start update"
          message={
            retryMutation.error instanceof Error
              ? retryMutation.error.message
              : String(retryMutation.error)
          }
        />
      ) : null}

      {ignoreMutation.isError ? (
        <StateBanner
          variant="error"
          title="Could not update ignore status"
          message={
            ignoreMutation.error instanceof Error
              ? ignoreMutation.error.message
              : String(ignoreMutation.error)
          }
        />
      ) : null}

      {bulkError ? (
        <StateBanner
          variant="error"
          title="Bulk action failed"
          message={bulkError}
        />
      ) : null}
    </section>
  );
}

function BulkActionsBar({
  selectedCount,
  bulkRunning,
  onIgnore,
  onRestore,
  onClear,
}: {
  selectedCount: number;
  bulkRunning: "ignore" | "restore" | null;
  onIgnore: () => void;
  onRestore: () => void;
  onClear: () => void;
}) {
  if (selectedCount === 0) return null;
  return (
    <div
      style={{
        alignItems: "center",
        background: "var(--color-surface-3)",
        border: "1px solid var(--color-action-primary)",
        borderRadius: "var(--radius-md)",
        display: "flex",
        flexWrap: "wrap",
        gap: 12,
        justifyContent: "space-between",
        padding: "8px 12px",
      }}
    >
      <span style={{ color: "var(--color-text-primary)", fontSize: "var(--text-sm)" }}>
        {selectedCount} selected
      </span>
      <div style={{ display: "flex", gap: 8 }}>
        <button
          type="button"
          onClick={onIgnore}
          disabled={bulkRunning != null}
          style={{
            background: "var(--color-surface-1)",
            border: "1px solid var(--color-border-subtle)",
            borderRadius: "var(--radius-sm)",
            color: "var(--color-text-primary)",
            cursor: bulkRunning ? "wait" : "pointer",
            fontSize: "var(--text-xs)",
            padding: "4px 10px",
          }}
        >
          {bulkRunning === "ignore" ? "Applying…" : "Ignore selected"}
        </button>
        <button
          type="button"
          onClick={onRestore}
          disabled={bulkRunning != null}
          style={{
            background: "var(--color-surface-1)",
            border: "1px solid var(--color-border-subtle)",
            borderRadius: "var(--radius-sm)",
            color: "var(--color-text-primary)",
            cursor: bulkRunning ? "wait" : "pointer",
            fontSize: "var(--text-xs)",
            padding: "4px 10px",
          }}
        >
          {bulkRunning === "restore" ? "Applying…" : "Restore selected"}
        </button>
        <button
          type="button"
          onClick={onClear}
          disabled={bulkRunning != null}
          style={{
            background: "transparent",
            border: "1px solid var(--color-border-subtle)",
            borderRadius: "var(--radius-sm)",
            color: "var(--color-text-tertiary)",
            cursor: "pointer",
            fontSize: "var(--text-xs)",
            padding: "4px 10px",
          }}
        >
          Clear
        </button>
      </div>
    </div>
  );
}

function SummaryCards({ data }: { data: DataCoverageResponse }) {
  const { summary } = data;
  const cards: Array<{ label: string; value: number; tone?: DataCoverageStatus }> = [
    { label: "Total in Universe", value: summary.total },
    { label: "Complete", value: summary.complete, tone: "complete" },
    { label: "Partial", value: summary.partial, tone: "partial" },
    { label: "No Data", value: summary.no_financial, tone: "no_financial" },
    { label: "Last Failed", value: summary.failed, tone: "failed" },
    { label: "Stale", value: summary.stale, tone: "partial" },
    { label: "Unmapped", value: summary.unmapped, tone: "unmapped" },
    { label: "Ignored", value: summary.ignored, tone: "ignored" },
  ];
  return (
    <div
      style={{
        display: "grid",
        gap: 12,
        gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
      }}
    >
      {cards.map((card) => {
        const tone = card.tone ? STATUS_TONE[card.tone] : null;
        return (
          <div
            key={card.label}
            style={{
              background: "var(--color-surface-2)",
              border: `1px solid ${tone?.border ?? "var(--color-border-subtle)"}`,
              borderRadius: "var(--radius-md)",
              padding: "12px 14px",
            }}
          >
            <div
              style={{
                color: tone?.fg ?? "var(--color-text-tertiary)",
                fontSize: "var(--text-xs)",
                fontWeight: 500,
                textTransform: "uppercase",
                letterSpacing: "0.04em",
              }}
            >
              {card.label}
            </div>
            <div
              style={{
                color: "var(--color-text-primary)",
                fontSize: "var(--text-2xl)",
                fontWeight: 600,
                marginTop: 4,
              }}
            >
              {card.value.toLocaleString("en-US")}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function FilterChips({
  data,
  current,
  onChange,
}: {
  data: DataCoverageResponse;
  current: DataCoverageFilterId;
  onChange: (id: DataCoverageFilterId) => void;
}) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {FILTERS.map((f) => {
        const active = f.id === current;
        const count = data.filter_counts[f.id] ?? 0;
        return (
          <button
            key={f.id}
            type="button"
            onClick={() => onChange(f.id)}
            style={{
              background: active ? "var(--color-surface-3)" : "var(--color-surface-1)",
              border: `1px solid ${active ? "var(--color-action-primary)" : "var(--color-border-subtle)"}`,
              borderRadius: 999,
              color: active ? "var(--color-text-primary)" : "var(--color-text-secondary)",
              cursor: "pointer",
              fontSize: "var(--text-xs)",
              padding: "4px 10px",
            }}
          >
            {f.label}
            <span
              style={{
                color: "var(--color-text-tertiary)",
                marginLeft: 6,
              }}
            >
              {count}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function CoverageTable({
  rows,
  onRetry,
  onToggleIgnored,
  retryingCvm,
  ignoringCvm,
  disabled,
  selected,
  onToggleSelected,
  onToggleSelectAll,
}: {
  rows: DataCoverageRow[];
  onRetry: (cdCvm: number) => void;
  onToggleIgnored: (row: DataCoverageRow) => void;
  retryingCvm: number | null;
  ignoringCvm: number | null;
  disabled: boolean;
  selected: Set<number>;
  onToggleSelected: (cdCvm: number) => void;
  onToggleSelectAll: (allSelected: boolean) => void;
}) {
  const allSelected = rows.length > 0 && rows.every((r) => selected.has(r.cd_cvm));
  const someSelected = rows.some((r) => selected.has(r.cd_cvm));
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(520);

  useLayoutEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;

    const updateViewport = () => {
      setViewportHeight(scroller.clientHeight || 520);
    };
    updateViewport();

    const resizeObserver =
      typeof ResizeObserver !== "undefined" ? new ResizeObserver(updateViewport) : null;
    resizeObserver?.observe(scroller);
    window.addEventListener("resize", updateViewport);

    return () => {
      resizeObserver?.disconnect();
      window.removeEventListener("resize", updateViewport);
    };
  }, []);

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (scroller) scroller.scrollTop = 0;
    setScrollTop(0);
  }, [rows]);

  const visibleCount = Math.max(1, Math.ceil(viewportHeight / VIRTUAL_ROW_HEIGHT));
  const startIndex = Math.max(0, Math.floor(scrollTop / VIRTUAL_ROW_HEIGHT) - VIRTUAL_OVERSCAN);
  const endIndex = Math.min(rows.length, startIndex + visibleCount + (VIRTUAL_OVERSCAN * 2));
  const virtualRows = rows.slice(startIndex, endIndex);
  const topSpacer = startIndex * VIRTUAL_ROW_HEIGHT;
  const bottomSpacer = Math.max(0, (rows.length - endIndex) * VIRTUAL_ROW_HEIGHT);

  return (
    <div
      ref={scrollerRef}
      onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
      style={{
        background: "var(--color-surface-2)",
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "var(--radius-md)",
        maxHeight: "min(68vh, 680px)",
        overflow: "auto",
      }}
    >
      <table
        style={{
          borderCollapse: "collapse",
          fontSize: "var(--text-sm)",
          minWidth: 1320,
          tableLayout: "fixed",
          width: "100%",
        }}
      >
        <colgroup>
          <col style={{ width: 44 }} />
          <col style={{ width: 280 }} />
          <col style={{ width: 90 }} />
          <col style={{ width: 82 }} />
          <col style={{ width: 150 }} />
          <col style={{ width: 72 }} />
          <col style={{ width: 92 }} />
          <col style={{ width: 150 }} />
          <col style={{ width: 260 }} />
          <col style={{ width: 200 }} />
        </colgroup>
        <thead>
          <tr
            style={{
              background: "var(--color-surface-1)",
              color: "var(--color-text-tertiary)",
              fontSize: "var(--text-xs)",
              textAlign: "left",
            }}
          >
            <Th>
              <input
                type="checkbox"
                aria-label="Select all"
                checked={allSelected}
                ref={(el) => {
                  if (el) el.indeterminate = !allSelected && someSelected;
                }}
                onChange={() => onToggleSelectAll(allSelected)}
              />
            </Th>
            <Th>Company</Th>
            <Th>Ticker</Th>
            <Th>CVM</Th>
            <Th>Status</Th>
            <Th>DFP</Th>
            <Th>ITR</Th>
            <Th>Last Update</Th>
            <Th>Error</Th>
            <Th>Actions</Th>
          </tr>
        </thead>
        <tbody>
          {topSpacer > 0 ? (
            <tr aria-hidden="true">
              <td colSpan={TABLE_COLUMN_COUNT} style={{ border: 0, height: topSpacer, padding: 0 }} />
            </tr>
          ) : null}
          {virtualRows.map((row) => {
            const tone = STATUS_TONE[row.status];
            return (
              <tr
                key={row.cd_cvm}
                style={{
                  borderTop: "1px solid var(--color-border-subtle)",
                  height: VIRTUAL_ROW_HEIGHT,
                }}
              >
                <Td>
                  <input
                    type="checkbox"
                    aria-label={`Select ${row.company_name}`}
                    checked={selected.has(row.cd_cvm)}
                    onChange={() => onToggleSelected(row.cd_cvm)}
                  />
                </Td>
                <Td>
                  <div
                    title={row.company_name}
                    style={{
                      color: "var(--color-text-primary)",
                      fontWeight: 500,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {row.company_name}
                  </div>
                </Td>
                <Td>{row.ticker ?? <Muted>—</Muted>}</Td>
                <Td>{row.cd_cvm}</Td>
                <Td>
                  <span
                    style={{
                      background: tone.bg,
                      border: `1px solid ${tone.border}`,
                      borderRadius: "var(--radius-sm)",
                      color: tone.fg,
                      display: "inline-block",
                      fontSize: "var(--text-xs)",
                      fontWeight: 500,
                      padding: "2px 8px",
                    }}
                  >
                    {STATUS_LABEL[row.status]}
                    {row.is_stale ? " · stale" : ""}
                  </span>
                </Td>
                <Td>{row.latest_dfp_year ?? <Muted>—</Muted>}</Td>
                <Td>{row.latest_itr_period ?? <Muted>—</Muted>}</Td>
                <Td>
                  {row.last_success_at ? (
                    <span title={row.last_success_at}>
                      {row.last_success_at.slice(0, 10)}
                    </span>
                  ) : row.last_attempt_at ? (
                    <span
                      title={row.last_attempt_at}
                      style={{ color: "var(--color-text-tertiary)" }}
                    >
                      {row.last_attempt_at.slice(0, 10)} (attempt)
                    </span>
                  ) : (
                    <Muted>never</Muted>
                  )}
                </Td>
                <Td>
                  {row.last_error ? (
                    <span
                      style={{
                        color: "var(--color-danger, #f87171)",
                        display: "inline-block",
                        maxWidth: 260,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                      title={row.last_error}
                    >
                      {row.last_error}
                    </span>
                  ) : (
                    <Muted>—</Muted>
                  )}
                </Td>
                <Td>
                  <div style={{ display: "flex", gap: 6, whiteSpace: "nowrap" }}>
                    {row.status === "failed" ? (
                      <button
                        type="button"
                        onClick={() => onRetry(row.cd_cvm)}
                        disabled={disabled || retryingCvm === row.cd_cvm}
                        style={{
                          background: "var(--color-surface-3)",
                          border: "1px solid var(--color-border-subtle)",
                          borderRadius: "var(--radius-sm)",
                          color: "var(--color-text-primary)",
                          cursor: disabled ? "not-allowed" : "pointer",
                          fontSize: "var(--text-xs)",
                          padding: "4px 8px",
                          opacity: disabled && retryingCvm !== row.cd_cvm ? 0.5 : 1,
                        }}
                      >
                        {retryingCvm === row.cd_cvm ? "Sending…" : "Retry"}
                      </button>
                    ) : null}
                    <Link
                      to={`/empresas/${row.cd_cvm}`}
                      style={{
                        background: "transparent",
                        border: "1px solid var(--color-border-subtle)",
                        borderRadius: "var(--radius-sm)",
                        color: "var(--color-text-secondary)",
                        fontSize: "var(--text-xs)",
                        padding: "4px 8px",
                        textDecoration: "none",
                      }}
                    >
                      Open
                    </Link>
                    <button
                      type="button"
                      onClick={() => onToggleIgnored(row)}
                      disabled={ignoringCvm === row.cd_cvm}
                      style={{
                        background: "transparent",
                        border: "1px solid var(--color-border-subtle)",
                        borderRadius: "var(--radius-sm)",
                        color: "var(--color-text-tertiary)",
                        cursor:
                          ignoringCvm === row.cd_cvm ? "not-allowed" : "pointer",
                        fontSize: "var(--text-xs)",
                        padding: "4px 8px",
                        opacity: ignoringCvm === row.cd_cvm ? 0.5 : 1,
                      }}
                    >
                      {ignoringCvm === row.cd_cvm
                        ? "…"
                        : row.ignored
                          ? "Restore"
                          : "Ignore"}
                    </button>
                  </div>
                </Td>
              </tr>
            );
          })}
          {bottomSpacer > 0 ? (
            <tr aria-hidden="true">
              <td colSpan={TABLE_COLUMN_COUNT} style={{ border: 0, height: bottomSpacer, padding: 0 }} />
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th
      style={{
        fontWeight: 500,
        padding: "8px 12px",
        position: "sticky",
        top: 0,
        textTransform: "uppercase",
        letterSpacing: "0.04em",
        zIndex: 1,
        background: "var(--color-surface-1)",
      }}
    >
      {children}
    </th>
  );
}

function Td({ children }: { children: React.ReactNode }) {
  return (
    <td
      style={{
        color: "var(--color-text-secondary)",
        padding: "10px 12px",
        verticalAlign: "middle",
      }}
    >
      {children}
    </td>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return (
    <span style={{ color: "var(--color-text-tertiary)" }}>{children}</span>
  );
}
