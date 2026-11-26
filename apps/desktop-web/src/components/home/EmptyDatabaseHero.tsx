import { Link } from "react-router-dom";

import { DataAction } from "@/components/shell/DataAction";
import { Button } from "@/components/ui/Button";
import { useLocalDatabaseState, useOnline } from "@/lib/api/localDatabase";
import { describeLocalDatabaseState } from "@/lib/localDatabase/describe";
import { openDataPanel } from "@/lib/localDatabase/panel";
import { showsHomeHero } from "@/lib/localDatabase/runStatus";

type Props = {
  onLoadRecommended: () => void;
  onChooseWidgets: () => void;
};

/**
 * Home lead while the local database has no statements (prototype variant E):
 * one primary action, layout choices kept as quiet secondary actions.
 */
export function EmptyDatabaseHero({ onLoadRecommended, onChooseWidgets }: Props) {
  const { data } = useLocalDatabaseState();
  const online = useOnline();
  if (!data || !showsHomeHero(data)) return null;

  const d = describeLocalDatabaseState(data, { online });
  const running = data.state === "files" || data.state === "updating";
  const title = running
    ? "Getting CVM data"
    : data.state === "failed"
      ? "The download didn't finish"
      : "No CVM data on this computer yet";

  return (
    <section aria-labelledby="empty-database-title" className="mx-auto mt-8 max-w-xl space-y-3 text-center">
      <p className="font-mono text-2xs uppercase tracking-wider" style={{ color: "var(--color-text-tertiary)" }}>
        Local database · {d.short.toLowerCase()}
      </p>
      <h3 id="empty-database-title" className="text-2xl font-semibold" style={{ color: "var(--color-text-primary)" }}>
        {title}
      </h3>
      {running ? (
        <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>{d.headline}</p>
      ) : null}
      <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>{d.detail}</p>
      {d.percent != null ? (
        <div className="mx-auto max-w-sm" aria-hidden="true" style={{ height: 6, background: "var(--color-surface-4)", borderRadius: 2, overflow: "hidden" }}>
          <div style={{ width: `${d.percent}%`, height: "100%", background: "var(--color-id-ticker)", transition: "width 180ms ease" }} />
        </div>
      ) : null}
      <p className="font-mono text-2xs" style={{ color: "var(--color-text-tertiary)" }}>
        Official CVM · DFP, ITR · every active company
      </p>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <DataAction state={data} online={online} context="inline" onViewProgress={openDataPanel} />
        {running ? (
          <Link to="/empresas" className="text-sm" style={{ color: "var(--color-id-link)" }}>
            Open Companies to watch progress →
          </Link>
        ) : null}
      </div>
      <div className="flex items-center justify-center gap-2 pt-2">
        <Button variant="ghost" size="xs" onClick={onLoadRecommended}>Load recommended layout</Button>
        <Button variant="ghost" size="xs" onClick={onChooseWidgets}>Choose widgets</Button>
      </div>
    </section>
  );
}
