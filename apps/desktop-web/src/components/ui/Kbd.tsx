import type { ReactNode } from "react";

/**
 * Minimal keyboard-shortcut badge. Used inside command-bar triggers,
 * shortcuts cheatsheet, and tooltip hints.
 */
export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd
      className="inline-flex h-[18px] min-w-[18px] shrink-0 items-center justify-center rounded-sm border px-1 font-mono text-[10px] leading-none whitespace-nowrap"
      style={{
        background: "var(--color-surface-3)",
        borderColor: "var(--color-border-strong)",
        color: "var(--color-text-secondary)",
      }}
    >
      {children}
    </kbd>
  );
}
