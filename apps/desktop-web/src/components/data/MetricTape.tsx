import type { ReactNode } from "react";

import { DeltaBadge } from "./DeltaBadge";
import { NumberCell, type NumberTone } from "./NumberCell";
import { Sparkline } from "./Sparkline";

export type MetricTapeItem = {
  id: string;
  label: string;
  value?: unknown;
  valueNode?: ReactNode;
  formatType?: unknown;
  tone?: NumberTone;
  sublabel?: ReactNode;
  delta?: unknown;
  sparkline?: Array<number | null | undefined>;
};

type MetricTapeProps = {
  items: MetricTapeItem[];
  ariaLabel?: string;
  className?: string;
};

export function MetricTape({
  items,
  ariaLabel = "Resumo de métricas",
  className,
}: MetricTapeProps) {
  if (items.length === 0) return null;

  return (
    <section
      className={className}
      aria-label={ariaLabel}
      style={{
        background: "var(--color-surface-2)",
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "var(--radius-md)",
        overflowX: "auto",
      }}
    >
      <div className="flex min-w-max">
        {items.map((item, index) => (
          <div
            key={item.id}
            style={{
              borderLeft:
                index === 0 ? "none" : "1px solid var(--color-border-subtle)",
              minWidth: 158,
              padding: "10px 12px",
            }}
          >
            <div className="flex items-start justify-between gap-3">
              <p
                style={{
                  color: "var(--color-text-tertiary)",
                  fontSize: "var(--text-xs)",
                  letterSpacing: "0.04em",
                  margin: 0,
                  textTransform: "uppercase",
                }}
              >
                {item.label}
              </p>
              {item.delta !== undefined ? <DeltaBadge value={item.delta} /> : null}
            </div>
            <div className="mt-2 flex items-end justify-between gap-3">
              <div className="min-w-0">
                {item.valueNode ?? (
                  <NumberCell
                    value={item.value}
                    formatType={item.formatType}
                    tone={item.tone ?? "neutral"}
                    size="lg"
                    align="left"
                  />
                )}
                {item.sublabel ? (
                  <p
                    className="truncate"
                    style={{
                      color: "var(--color-text-tertiary)",
                      fontSize: "var(--text-xs)",
                      margin: "3px 0 0",
                    }}
                  >
                    {item.sublabel}
                  </p>
                ) : null}
              </div>
              {item.sparkline ? (
                <Sparkline
                  values={item.sparkline}
                  label={`${item.label} sparkline`}
                  width={76}
                  height={24}
                />
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
