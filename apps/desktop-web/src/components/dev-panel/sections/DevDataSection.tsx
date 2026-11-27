import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { StateBanner } from "@/components/feedback/StateBanner";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { DEV_DATA_QUERY_KEY, fetchDevDataInfo, runDevDataAction } from "@/lib/api/devPanel";
import type { DevDataInfo, DevDataOperation, DevDataTarget, DevDataTargetInfo } from "@/lib/bridge/types.dev";

import { SectionFrame } from "../SectionFrame";
import type { DevPanelSection } from "../sections";

const TARGET_LABEL: Record<DevDataTarget, string> = {
  db: "Database",
  input: "Downloaded CVM files",
  all: "Everything",
};

const ACTION_LABEL: Record<DevDataOperation, string> = {
  backup: "Move to backup",
  restore: "Restore backup",
  delete: "Delete permanently",
};

const CLOSING: Record<DevDataOperation, (label: string) => string> = {
  backup: (label) => `move ${label} to backup`,
  restore: (label) => `restore the ${label} backup`,
  delete: (label) => `delete ${label}`,
};

const SHARED_WARNING ="Shared dev data: this affects every worktree that uses it.";
const DANGER_OUTLINE = { color: "var(--color-state-err)", borderColor: "var(--color-state-err)" };

/** Binary units, as Windows Explorer shows them. */
export function formatBytes(bytes: number | null): string {
  if (bytes === null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = bytes;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${unit === 0 ? size : size.toFixed(size >= 10 ? 1 : 2)} ${units[unit]}`;
}

function sizeText(exists: boolean, bytes: number | null, missing: string): string {
  return exists ? formatBytes(bytes) : missing;
}

/** Where a target's data lives when it differs from the rest of this window's dev data. */
function targetNote(item: DevDataTargetInfo, info: DevDataInfo): string | null {
  const downloadsShared = info.targets.some((t) => t.target === "input" && t.shared);
  const ownData = info.targets.some((t) => !t.shared);
  if (!ownData || !downloadsShared) return null;
  if (item.target === "input") return "Shared folder: isolated dev data reads downloaded CVM files from shared dev data.";
  if (item.target === "all") return "This worktree's own data; downloaded CVM files stay in the shared folder.";
  return null;
}

type ConfirmProps = {
  operation: DevDataOperation;
  item: DevDataTargetInfo;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (confirm: string) => void;
};

/** Confirmation of one data action: target, paths, sizes, what is lost, and the shared-data warning. */
export function DataActionConfirm({ operation, item, busy, onCancel, onConfirm }: ConfirmProps) {
  const [typed, setTyped] = useState("");
  const label = TARGET_LABEL[item.target];
  const deleting = operation === "delete";
  const current = sizeText(item.exists, item.size_bytes, "not present");
  const backup = sizeText(item.backup_exists, item.backup_size_bytes, "none");
  const title = {
    backup: `Move ${label} to backup?`,
    restore: `Restore the ${label} backup?`,
    delete: `Delete ${label} permanently?`,
  }[operation];
  const consequence = {
    backup: item.backup_exists ? `The current backup (${backup}) is deleted and replaced.` : "There is no backup yet.",
    restore: item.exists
      ? `Current data (${current}) is deleted and replaced with the backup.`
      : "There is no current data; the backup becomes current data.",
    delete: `This cannot be undone. ${item.backup_exists ? `The backup (${backup}) is kept.` : "There is no backup."}`,
  }[operation];
  const does = { backup: "moves the data", restore: "restores the backup", delete: "deletes the data" }[operation];
  const resetsDatabase = operation !== "restore" && item.target !== "input";

  return (
    <div
      role="group"
      aria-label={title}
      className="flex flex-col gap-2 rounded-md p-2"
      style={{
        border: `1px solid ${deleting ? "var(--color-state-err)" : "var(--color-state-warn)"}`,
        background: "var(--color-surface-1)",
      }}
    >
      <p className="text-sm font-semibold" style={{ color: "var(--color-text-primary)", margin: 0 }}>
        {title}
      </p>
      <dl
        className="grid items-baseline gap-x-2 gap-y-1 text-xs"
        style={{ gridTemplateColumns: "max-content minmax(0, 1fr)", margin: 0 }}
      >
        <dt style={{ color: "var(--color-text-tertiary)" }}>Current</dt>
        <dd className="font-mono" style={{ margin: 0, overflowWrap: "anywhere", color: "var(--color-text-primary)" }}>
          {item.path} ({current})
        </dd>
        <dt style={{ color: "var(--color-text-tertiary)" }}>Backup</dt>
        <dd className="font-mono" style={{ margin: 0, overflowWrap: "anywhere", color: "var(--color-text-primary)" }}>
          {item.backup_path} ({backup})
        </dd>
      </dl>
      <p className="text-xs" style={{ color: "var(--color-text-secondary)", margin: 0 }}>
        {consequence}
      </p>
      {item.shared ? (
        <p className="text-xs" style={{ color: "var(--color-state-warn)", margin: 0 }}>
          ▲ {SHARED_WARNING}
        </p>
      ) : null}
      <p className="text-xs" style={{ color: "var(--color-text-tertiary)", margin: 0 }}>
        The app closes, {does} and reopens{resetsDatabase ? " on its empty first-run state" : ""}.
      </p>
      {deleting ? (
        <label className="flex flex-col gap-1 text-xs" style={{ color: "var(--color-text-secondary)" }}>
          <span>
            Type <code className="font-mono">{item.target}</code> to confirm
          </span>
          <Input mono autoFocus value={typed} onChange={(event) => setTyped(event.target.value)} style={{ padding: "2px 8px" }} />
        </label>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" size="xs" onClick={onCancel} disabled={busy} autoFocus={!deleting}>
          Cancel
        </Button>
        <Button
          variant={deleting ? "danger" : "primary"}
          size="xs"
          loading={busy}
          disabled={deleting && typed !== item.target}
          onClick={() => onConfirm(typed)}
        >
          {ACTION_LABEL[operation]}
        </Button>
      </div>
    </div>
  );
}

type Pending = { operation: DevDataOperation; target: DevDataTarget };

function TargetRow({
  item,
  info,
  pending,
  busy,
  onPick,
  onConfirm,
}: {
  item: DevDataTargetInfo;
  info: DevDataInfo;
  pending: Pending | null;
  busy: boolean;
  onPick: (pending: Pending | null) => void;
  onConfirm: (pending: Pending, confirm: string) => void;
}) {
  const note = targetNote(item, info);
  const blocked = busy || !info.supervised;
  const picked = pending?.target === item.target ? pending : null;
  return (
    <li className="flex flex-col gap-1 py-2" style={{ borderTop: "1px solid var(--color-border-subtle)" }}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm" style={{ color: "var(--color-text-primary)" }}>
          {TARGET_LABEL[item.target]}
          {item.shared ? (
            <span
              className="ml-2 rounded-sm border px-1 font-mono text-2xs uppercase tracking-wider"
              style={{ borderColor: "var(--color-state-warn)", color: "var(--color-state-warn)" }}
            >
              Shared
            </span>
          ) : null}
        </span>
        <span className="font-mono text-sm" style={{ color: "var(--color-text-primary)", fontVariantNumeric: "tabular-nums" }}>
          {sizeText(item.exists, item.size_bytes, "Not present")}
        </span>
      </div>
      <div className="font-mono text-2xs" style={{ color: "var(--color-text-tertiary)", overflowWrap: "anywhere" }}>
        {item.path}
      </div>
      <div className="text-xs" style={{ color: "var(--color-text-secondary)" }}>
        {item.backup_exists ? `Backup: ${formatBytes(item.backup_size_bytes)}` : "No backup"}
      </div>
      {note ? (
        <div className="text-2xs" style={{ color: "var(--color-text-tertiary)" }}>
          {note}
        </div>
      ) : null}
      {picked ? (
        <DataActionConfirm
          operation={picked.operation}
          item={item}
          busy={busy}
          onCancel={() => onPick(null)}
          onConfirm={(confirm) => onConfirm(picked, confirm)}
        />
      ) : (
        <div className="flex flex-wrap gap-1">
          <Button
            size="xs"
            disabled={blocked || !item.exists}
            title={item.exists ? undefined : "Nothing to move: the folder does not exist."}
            onClick={() => onPick({ operation: "backup", target: item.target })}
          >
            {ACTION_LABEL.backup}
          </Button>
          <Button
            size="xs"
            disabled={blocked || !item.backup_exists}
            title={item.backup_exists ? undefined : "There is no backup to restore."}
            onClick={() => onPick({ operation: "restore", target: item.target })}
          >
            {ACTION_LABEL.restore}
          </Button>
          <Button
            size="xs"
            style={DANGER_OUTLINE}
            disabled={blocked || !item.exists}
            title={item.exists ? undefined : "Nothing to delete: the folder does not exist."}
            onClick={() => onPick({ operation: "delete", target: item.target })}
          >
            Delete
          </Button>
        </div>
      )}
    </li>
  );
}

function DevDataSection() {
  const info = useQuery({ queryKey: DEV_DATA_QUERY_KEY, queryFn: fetchDevDataInfo, staleTime: 0, retry: false });
  const [pending, setPending] = useState<Pending | null>(null);
  const action = useMutation({
    mutationFn: ({ operation, target, confirm }: Pending & { confirm: string }) =>
      runDevDataAction(operation, target, confirm),
  });
  // After an accepted action the window closes; nothing else may start meanwhile.
  const busy = action.isPending || action.isSuccess;
  const data = info.data;

  return (
    <SectionFrame
      title="Dev data"
      action={
        <Button variant="ghost" size="xs" onClick={() => void info.refetch()} disabled={info.isFetching || busy}>
          {info.isFetching ? "Refreshing…" : "Refresh"}
        </Button>
      }
    >
      {info.isPending ? (
        <StateBanner variant="loading" size="dense" title="Reading dev data…" />
      ) : info.isError ? (
        <StateBanner
          variant="error"
          size="dense"
          title="Dev data unavailable"
          message={info.error.message}
          onRetry={() => void info.refetch()}
        />
      ) : data && data.unavailable_reason ? (
        <StateBanner variant="warning" size="dense" title="Data actions unavailable" message={data.unavailable_reason} />
      ) : data ? (
        <>
          {data.targets.every((t) => t.shared) ? (
            <p className="text-xs" style={{ color: "var(--color-state-warn)", margin: 0 }}>
              ▲ {SHARED_WARNING}
            </p>
          ) : null}
          {!data.supervised ? (
            <p className="text-xs" style={{ color: "var(--color-text-secondary)", margin: 0 }}>
              No dev supervisor: data actions need the app started with python -m desktop.app --dev.
            </p>
          ) : null}
          <ul className="flex flex-col" style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {data.targets.map((item) => (
              <TargetRow
                key={item.target}
                item={item}
                info={data}
                pending={pending}
                busy={busy}
                onPick={setPending}
                onConfirm={(picked, confirm) => action.mutate({ ...picked, confirm })}
              />
            ))}
          </ul>
          {action.isSuccess && action.variables ? (
            <p className="text-xs" role="status" style={{ color: "var(--color-text-secondary)", margin: 0 }}>
              ● The app is closing to {CLOSING[action.variables.operation](TARGET_LABEL[action.variables.target])}. It
              reopens when done; the terminal shows the outcome.
            </p>
          ) : null}
          {action.error ? (
            <p className="text-xs" role="alert" style={{ color: "var(--color-state-err)", margin: 0 }}>
              ! {action.error.message}
            </p>
          ) : null}
          {data.last_action ? (
            data.last_action.ok ? (
              <p className="text-xs" style={{ color: "var(--color-text-secondary)", margin: 0 }}>
                ● Last action ({data.last_action.finished_at}): {data.last_action.message}
              </p>
            ) : (
              <StateBanner
                variant="error"
                size="dense"
                title={`Last data action failed (${data.last_action.finished_at})`}
                message={data.last_action.message}
              />
            )
          ) : null}
        </>
      ) : null}
    </SectionFrame>
  );
}

export const section: DevPanelSection = { id: "data", order: 400, Component: DevDataSection };
