import type { ReactNode } from "react";

import { DataShellAside, useDataShellAsideWidth } from "@/prototypes/dataShell/slots";

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
  const asideWidth = useDataShellAsideWidth();
  return (
    <div
      className="grid h-full w-full"
      style={{
        gridTemplateColumns: asideWidth ? `minmax(0, 1fr) ${asideWidth}px` : "minmax(0, 1fr)",
        gridTemplateRows: "36px 32px 1fr 24px",
        gridTemplateAreas: asideWidth
          ? '"top top" "subnav subnav" "main aside" "status status"'
          : '"top" "subnav" "main" "status"',
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
          minWidth: 0,
          minHeight: 0,
          overflow: "auto",
          padding: "var(--spacing-4)",
        }}
      >
        {children}
      </main>
      <DataShellAside />
      <div style={{ gridArea: "status" }}>
        <StatusStrip />
      </div>
    </div>
  );
}
