import type { ReactNode } from "react";

import { SkeletonRow } from "./Skeleton";

/**
 * Unified loading / empty / error / browser-only state surface. Replaces
 * the per-route `CardSkeleton`, `EmptyState`, `BrowserModeBanner`, and
 * `ErrorState` inline definitions.
 *
 * Visual contract:
 *   loading       — surface-2 panel + subtitle "Loading…" + 3-line skeleton
 *   empty         — surface-2 panel + title + body, muted
 *   error         — error-toned border + title + message, optional retry
 *   browser-only  — warn-toned border + title + reason
 *
 * All variants paint at the same width/height ratio so a route doesn't
 * shift layout when state transitions. Pair the variant glyph (●/◌/!/▲)
 * with the color so the signal is not color-only.
 */

type Variant = "loading" | "empty" | "error" | "browser-only";

type Props = {
  variant: Variant;
  title?: string;
  message?: string;
  /** Only meaningful for `error`. */
  onRetry?: () => void;
  /** Optional slot below body. */
  children?: ReactNode;
  /** Visual size — default is `comfortable`. `dense` is for inline cells. */
  size?: "dense" | "comfortable";
};

const VARIANTS: Record<
  Variant,
  { glyph: string; defaultTitle: string; color: string; border: string; bg: string; role: "status" | "alert" }
> = {
  loading: {
    glyph: "◌",
    defaultTitle: "Loading…",
    color: "var(--color-text-secondary)",
    border: "var(--color-border-subtle)",
    bg: "var(--color-surface-2)",
    role: "status",
  },
  empty: {
    glyph: "—",
    defaultTitle: "Sem dados",
    color: "var(--color-text-secondary)",
    border: "var(--color-border-subtle)",
    bg: "var(--color-surface-2)",
    role: "status",
  },
  error: {
    glyph: "!",
    defaultTitle: "Erro",
    color: "var(--color-state-err)",
    border: "var(--color-state-err)",
    bg: "var(--color-surface-2)",
    role: "alert",
  },
  "browser-only": {
    glyph: "▲",
    defaultTitle: "Modo navegador",
    color: "var(--color-state-warn)",
    border: "var(--color-state-warn)",
    bg: "var(--color-surface-2)",
    role: "status",
  },
};

export function StateBanner({
  variant,
  title,
  message,
  onRetry,
  children,
  size = "comfortable",
}: Props) {
  const v = VARIANTS[variant];
  const shownTitle = title ?? v.defaultTitle;
  const pad = size === "dense" ? "12px 16px" : "16px 20px";

  return (
    <div
      role={v.role}
      aria-live={v.role === "status" ? "polite" : undefined}
      style={{
        background: v.bg,
        border: `1px solid ${v.border}`,
        borderRadius: "var(--radius-md)",
        padding: pad,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          aria-hidden="true"
          className="font-mono"
          style={{
            color: v.color,
            fontSize: "var(--text-md)",
            width: 14,
            textAlign: "center",
          }}
        >
          {v.glyph}
        </span>
        <span
          style={{
            color: v.color,
            fontSize: "var(--text-sm)",
            fontWeight: 500,
            letterSpacing: "0.02em",
            textTransform: "uppercase",
          }}
        >
          {shownTitle}
        </span>
        {onRetry && variant === "error" ? (
          <button
            type="button"
            onClick={onRetry}
            className="ml-auto font-mono"
            style={{
              fontSize: "var(--text-xs)",
              color: "var(--color-action-primary)",
              background: "transparent",
              border: "1px solid var(--color-border-default)",
              padding: "2px 8px",
              borderRadius: "var(--radius-sm)",
              cursor: "pointer",
            }}
          >
            tentar novamente
          </button>
        ) : null}
      </div>
      {message ? (
        <p
          style={{
            color: "var(--color-text-secondary)",
            fontSize: "var(--text-sm)",
            margin: 0,
          }}
        >
          {message}
        </p>
      ) : null}
      {variant === "loading" && !children ? (
        <SkeletonRow lines={3} />
      ) : null}
      {children}
    </div>
  );
}
