import type { ReactNode } from "react";

import { Input } from "@/components/ui/Input";

type TableToolbarProps = {
  search?: string;
  onSearchChange?: (value: string) => void;
  searchPlaceholder?: string;
  meta?: ReactNode;
  actions?: ReactNode;
};

export function TableToolbar({
  search,
  onSearchChange,
  searchPlaceholder = "Filter rows...",
  meta,
  actions,
}: TableToolbarProps) {
  return (
    <div
      className="flex flex-wrap items-center gap-3"
      style={{
        borderBottom: "1px solid var(--color-border-subtle)",
        padding: "10px 12px",
      }}
    >
      {onSearchChange ? (
        <label className="min-w-64 flex-1">
          <span className="sr-only">{searchPlaceholder}</span>
          <Input
            type="search"
            value={search ?? ""}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder={searchPlaceholder}
            style={{
              background: "var(--color-surface-1)",
              height: 30,
              fontSize: "var(--text-sm)",
            }}
          />
        </label>
      ) : null}
      {meta ? (
        <div
          className="font-mono"
          style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-xs)" }}
        >
          {meta}
        </div>
      ) : null}
      {actions ? <div className="ml-auto flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}
