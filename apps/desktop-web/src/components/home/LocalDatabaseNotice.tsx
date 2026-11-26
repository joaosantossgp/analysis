import { DataAction } from "@/components/shell/DataAction";
import { Button } from "@/components/ui/Button";
import { useLocalDatabaseState, useOnline } from "@/lib/api/localDatabase";
import { describeLocalDatabaseState, LOCAL_DATABASE_TONE_COLOR } from "@/lib/localDatabase/describe";
import { openDataPanel } from "@/lib/localDatabase/panel";

/** Slim Home notice when the local database has data but needs attention. */
export function LocalDatabaseNotice() {
  const { data } = useLocalDatabaseState();
  const online = useOnline();
  if (!data || (data.state !== "stale" && data.state !== "partial")) return null;

  const d = describeLocalDatabaseState(data, { online });
  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-3 px-3 py-2 text-xs"
      style={{ background: "var(--color-surface-2)", border: "1px solid var(--color-border-default)", borderRadius: "var(--radius-md)" }}
    >
      <span style={{ color: LOCAL_DATABASE_TONE_COLOR[d.tone] }}>
        <span aria-hidden="true">{d.glyph} </span>
        {d.headline}
      </span>
      <span style={{ color: "var(--color-text-tertiary)" }}>{d.detail}</span>
      <span className="ml-auto">
        {data.state === "partial" ? (
          <Button variant="secondary" size="xs" onClick={openDataPanel}>View failures</Button>
        ) : (
          <DataAction state={data} online={online} context="inline" size="xs" onViewProgress={openDataPanel} />
        )}
      </span>
    </div>
  );
}
