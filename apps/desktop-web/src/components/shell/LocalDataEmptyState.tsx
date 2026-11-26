import { StateBanner } from "@/components/feedback/StateBanner";
import { useLocalDatabaseState, useOnline } from "@/lib/api/localDatabase";
import { openDataPanel } from "@/lib/localDatabase/panel";

import { DataAction } from "./DataAction";

type Props = {
  title: string;
  /** Shown when the cause is an empty local database. */
  emptyMessage: string;
  /** Shown when data exists and the screen is empty for its own reason. */
  fallbackMessage: string;
};

/**
 * Empty state for data-dependent screens. When the local database is empty it
 * offers the shared data update action instead of a dead end (ADR 0010).
 */
export function LocalDataEmptyState({ title, emptyMessage, fallbackMessage }: Props) {
  const { data } = useLocalDatabaseState();
  const online = useOnline();
  const databaseEmpty = Boolean(data && data.state !== "unknown" && !data.has_statements);

  return (
    <StateBanner variant="empty" title={title} message={databaseEmpty ? emptyMessage : fallbackMessage}>
      {databaseEmpty && data ? (
        <div className="mt-3 space-y-2">
          <DataAction state={data} online={online} context="inline" onViewProgress={openDataPanel} />
          <p className="font-mono text-2xs" style={{ color: "var(--color-text-tertiary)" }}>
            Official CVM · DFP, ITR
          </p>
        </div>
      ) : null}
    </StateBanner>
  );
}
