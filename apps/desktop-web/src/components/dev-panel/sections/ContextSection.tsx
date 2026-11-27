import type { ReactNode } from "react";

import { StateBanner } from "@/components/feedback/StateBanner";
import { Button } from "@/components/ui/Button";
import type { DevContext, DevDataMode } from "@/lib/bridge/types.dev";

import { SectionFrame, Tag } from "../SectionFrame";
import type { DevPanelSection } from "../sections";
import { useDevContext } from "../useDevContext";

const DATA_MODE_LABEL: Record<DevDataMode, string> = {
  shared: "Shared dev data",
  isolated: "Isolated dev data (own databases, shared downloads)",
  "full-copy": "Isolated dev data (full copy)",
  "installed-app": "Installed-app data (Documents\\CVMAnalytics)",
  custom: "Custom data directory (CVM_DATA_DIR)",
};

/** Modes where an action in this window does not touch shared dev data. */
const DATA_MODE_INDICATOR: Partial<Record<DevDataMode, string>> = {
  isolated: "Isolated data",
  "full-copy": "Isolated data",
  "installed-app": "Installed-app data",
};

const MISSING = "—";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-xs" style={{ color: "var(--color-text-tertiary)" }}>{label}</dt>
      <dd className="font-mono text-sm" style={{ color: "var(--color-text-primary)", margin: 0, minWidth: 0, overflowWrap: "anywhere" }}>
        {children}
      </dd>
    </>
  );
}

function ContextRows({ context }: { context: DevContext }) {
  const indicator = DATA_MODE_INDICATOR[context.data_mode];
  return (
    <>
      <dl className="grid items-baseline gap-x-3 gap-y-1" style={{ gridTemplateColumns: "max-content minmax(0, 1fr)", margin: 0 }}>
        <Row label="Worktree">
          {context.worktree}
          {context.is_main_checkout ? <Tag color="var(--color-text-secondary)">Main checkout</Tag> : null}
          <div className="text-2xs" style={{ color: "var(--color-text-tertiary)" }}>{context.worktree_path}</div>
        </Row>
        <Row label="Branch">{context.branch ?? (context.git_error ? MISSING : "Detached HEAD")}</Row>
        <Row label="Commit">{context.commit ?? MISSING}</Row>
        <Row label="Changes">
          {context.dirty === null ? (
            MISSING
          ) : context.dirty ? (
            <span style={{ color: "var(--color-state-warn)" }}>● Uncommitted changes</span>
          ) : (
            <span style={{ color: "var(--color-text-secondary)" }}>No uncommitted changes</span>
          )}
        </Row>
        <Row label="Data">
          {DATA_MODE_LABEL[context.data_mode]}
          {indicator ? (
            <Tag color="var(--color-state-warn)">
              <span aria-hidden="true">▲</span>
              {indicator}
            </Tag>
          ) : null}
        </Row>
        <Row label="Data path">{context.data_path}</Row>
      </dl>
      {context.git_error ? (
        <StateBanner variant="warning" size="dense" title="Git state unavailable" message={context.git_error} />
      ) : null}
    </>
  );
}

function ContextSection() {
  const context = useDevContext();
  return (
    <SectionFrame
      title="Context"
      action={
        <Button variant="ghost" size="xs" onClick={() => void context.refetch()} disabled={context.isFetching}>
          {context.isFetching ? "Refreshing…" : "Refresh"}
        </Button>
      }
    >
      {context.isPending ? (
        <StateBanner variant="loading" size="dense" title="Reading dev context…" />
      ) : context.isError ? (
        <StateBanner
          variant="error"
          size="dense"
          title="Dev context unavailable"
          message={context.error.message}
          onRetry={() => void context.refetch()}
        />
      ) : (
        <ContextRows context={context.data} />
      )}
    </SectionFrame>
  );
}

export const section: DevPanelSection = { id: "context", order: 100, Component: ContextSection };
