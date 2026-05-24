import type { ReactNode } from "react";

import { StatusStrip } from "./StatusStrip";
import { SubNav } from "./SubNav";
import { TopBar } from "./TopBar";

type Props = {
  children: ReactNode;
  /** Opens the command palette. Optional so the shell still renders standalone. */
  onOpenPalette?: () => void;
};

/**
 * Full-bleed terminal shell. CSS grid: top bar (36) / sub-nav (32) /
 * main outlet (1fr) / status strip (24). Replaces the previous centered
 * `max-w-5xl` container in App.tsx.
 */
export function TerminalShell({ children, onOpenPalette }: Props) {
  return (
    <div
      className="grid h-full w-full"
      style={{
        gridTemplateRows: "36px 32px 1fr 24px",
        gridTemplateAreas: '"top" "subnav" "main" "status"',
        background: "var(--color-surface-1)",
        color: "var(--color-text-primary)",
      }}
    >
      <div style={{ gridArea: "top" }}>
        <TopBar onOpenPalette={onOpenPalette} />
      </div>
      <div style={{ gridArea: "subnav" }}>
        <SubNav />
      </div>
      <main
        style={{
          gridArea: "main",
          overflow: "auto",
          padding: "var(--spacing-4)",
        }}
      >
        {children}
      </main>
      <div style={{ gridArea: "status" }}>
        <StatusStrip />
      </div>
    </div>
  );
}
