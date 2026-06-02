import type { IndicatorRecord } from "@/lib/indicators/registry";
import { formatLatestValue } from "@/lib/indicators/registry";

import { StatusBadge, Tag } from "./StatusBadge";

interface IndicatorCatalogTableProps {
  records: IndicatorRecord[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  isFavorite: (id: string) => boolean;
  onToggleFavorite: (id: string) => void;
}

/**
 * The catalog as a dense, sticky-header table. Intentionally renders NO charts —
 * a few hundred rows of plain DOM scroll fine; if the catalog grows toward
 * thousands, swap the <tbody> map for a windowed list (e.g. virtual rows) — the
 * row markup is already self-contained.
 */
export function IndicatorCatalogTable({
  records,
  selectedId,
  onSelect,
  isFavorite,
  onToggleFavorite,
}: IndicatorCatalogTableProps) {
  return (
    <div
      style={{
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "var(--radius-md)",
        maxHeight: "calc(100vh - 320px)",
        minHeight: 240,
        overflow: "auto",
      }}
    >
      <table className="w-full border-collapse" style={{ fontSize: "var(--text-sm)" }}>
        <thead>
          <tr
            style={{
              background: "var(--color-surface-2)",
              color: "var(--color-text-tertiary)",
              position: "sticky",
              top: 0,
              zIndex: 1,
            }}
          >
            <Th style={{ width: 28 }} aria-label="Favorite" />
            <Th>Indicator</Th>
            <Th>Source</Th>
            <Th>Theme</Th>
            <Th align="right">Latest</Th>
            <Th align="right">Reference</Th>
            <Th>Freq</Th>
            <Th>Status</Th>
          </tr>
        </thead>
        <tbody>
          {records.map((r) => {
            const selected = r.id === selectedId;
            const fav = isFavorite(r.id);
            return (
              <tr
                key={r.id}
                role="button"
                tabIndex={0}
                aria-pressed={selected}
                onClick={() => onSelect(r.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelect(r.id);
                  }
                }}
                style={{
                  background: selected ? "var(--color-surface-3)" : "transparent",
                  borderTop: "1px solid var(--color-border-subtle)",
                  cursor: "pointer",
                }}
                className="hover:brightness-125"
              >
                <Td>
                  <button
                    type="button"
                    aria-label={fav ? "Remove from favorites" : "Add to favorites"}
                    aria-pressed={fav}
                    onClick={(e) => {
                      e.stopPropagation();
                      onToggleFavorite(r.id);
                    }}
                    style={{
                      background: "transparent",
                      border: "none",
                      color: fav ? "var(--color-action-primary)" : "var(--color-text-disabled)",
                      cursor: "pointer",
                      fontSize: "var(--text-md)",
                      lineHeight: 1,
                      padding: 0,
                    }}
                  >
                    {fav ? "★" : "☆"}
                  </button>
                </Td>
                <Td>
                  <div style={{ color: "var(--color-text-primary)" }} title={r.description || r.name}>
                    {r.name}
                  </div>
                  <div
                    className="font-mono truncate"
                    style={{
                      color: "var(--color-text-tertiary)",
                      fontSize: "var(--text-2xs)",
                      maxWidth: 320,
                    }}
                  >
                    {r.unit ? `${r.unit} · ` : ""}
                    {r.valueType === "derived" ? "derived" : "raw"}
                  </div>
                </Td>
                <Td>
                  <Tag title={r.primarySource}>{r.sourceLabel}</Tag>
                </Td>
                <Td style={{ color: "var(--color-text-secondary)" }}>{r.theme}</Td>
                <Td align="right">
                  <span
                    className="font-mono"
                    style={{
                      color: "var(--color-text-primary)",
                      fontVariantNumeric: "tabular-nums",
                      whiteSpace: "nowrap",
                    }}
                    title={r.latestValueLabel ? `Reference: ${r.latestValueLabel}` : undefined}
                  >
                    {formatLatestValue(r.latestValue, r.unit)}
                  </span>
                </Td>
                <Td align="right">
                  <span
                    className="font-mono"
                    style={{
                      color: "var(--color-text-tertiary)",
                      fontSize: "var(--text-2xs)",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {formatRef(r.latestReferenceDate)}
                  </span>
                </Td>
                <Td style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)" }}>
                  {r.frequency}
                </Td>
                <Td>
                  <StatusBadge status={r.status} />
                </Td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Th({
  children,
  align = "left",
  style,
  "aria-label": ariaLabel,
}: {
  children?: React.ReactNode;
  align?: "left" | "right";
  style?: React.CSSProperties;
  "aria-label"?: string;
}) {
  return (
    <th
      aria-label={ariaLabel}
      style={{
        fontSize: "var(--text-2xs)",
        fontWeight: 500,
        letterSpacing: "0.04em",
        padding: "8px 10px",
        textAlign: align,
        textTransform: "uppercase",
        whiteSpace: "nowrap",
        ...style,
      }}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  align = "left",
  style,
}: {
  children?: React.ReactNode;
  align?: "left" | "right";
  style?: React.CSSProperties;
}) {
  return (
    <td style={{ padding: "8px 10px", textAlign: align, verticalAlign: "top", ...style }}>
      {children}
    </td>
  );
}

/** Year refs render as-is; datetime refs collapse to a short date. */
function formatRef(value: string | null): string {
  if (!value) return "—";
  if (/^\d{4}$/.test(value)) return value;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value.slice(0, 10);
  return d.toLocaleDateString("en-US", { year: "2-digit", month: "short", day: "2-digit" });
}
