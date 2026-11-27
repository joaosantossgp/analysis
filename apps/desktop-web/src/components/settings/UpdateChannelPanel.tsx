import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { StateBanner } from "@/components/feedback/StateBanner";
import { Panel } from "@/components/surface/Panel";
import { Button } from "@/components/ui/Button";
import {
  fetchStoredUpdateCheck,
  fetchUpdateChannel,
  saveUpdateChannel,
  triggerCheckUpdate,
  UPDATE_CHECK_KEY,
} from "@/lib/api/appStatus";
import type { UpdateChannel, UpdateCheckResult } from "@/lib/bridge/types";

const CHANNEL_OPTIONS: Array<{ value: UpdateChannel; label: string; description: string }> = [
  {
    value: "releases",
    label: "Releases only (default)",
    description: "Updates arrive when a publication is offered to every installed app.",
  },
  {
    value: "prereleases",
    label: "Pre-releases and releases",
    description: "Pre-releases bring features sooner and may be less stable.",
  },
];

export type UpdateChannelViewProps = {
  loading: boolean;
  loadError: string | null;
  browserReason: string | null;
  channel: UpdateChannel | null;
  check: UpdateCheckResult | null;
  checking: boolean;
  saving: boolean;
  saveError: string | null;
  onChange: (channel: UpdateChannel) => void;
  onCheck: () => void;
  onRetry: () => void;
};

/** Settings -> App: the update channel of the installed app (ADR 0011). */
export function UpdateChannelPanel({ bridgeReady }: { bridgeReady: boolean }) {
  const queryClient = useQueryClient();
  const channelQuery = useQuery({
    queryKey: ["update-channel"],
    queryFn: fetchUpdateChannel,
    enabled: bridgeReady,
    refetchOnWindowFocus: false,
  });
  const desktop = channelQuery.data?.mode === "desktop";
  // Reads the status of the last check (startup or "Check now"); it does not contact GitHub.
  const checkQuery = useQuery({
    queryKey: UPDATE_CHECK_KEY,
    queryFn: fetchStoredUpdateCheck,
    enabled: desktop,
    refetchOnWindowFocus: false,
  });
  const check = useMutation({
    mutationFn: () => triggerCheckUpdate({ force: true }),
    onSuccess: (result) => queryClient.setQueryData(UPDATE_CHECK_KEY, result),
  });
  const save = useMutation({
    mutationFn: saveUpdateChannel,
    onSuccess: (channel) => {
      queryClient.setQueryData(["update-channel"], { mode: "desktop", channel });
      // Saving already checked the new channel: read that stored result, do not ask GitHub again.
      void queryClient.invalidateQueries({ queryKey: UPDATE_CHECK_KEY });
    },
  });
  const failure = channelQuery.error ?? checkQuery.error ?? check.error;

  return (
    <UpdateChannelView
      loading={!bridgeReady || channelQuery.isLoading}
      loadError={failure ? errorMessage(failure) : null}
      browserReason={channelQuery.data?.mode === "browser" ? channelQuery.data.reason : null}
      channel={channelQuery.data?.channel ?? null}
      check={checkQuery.data ?? null}
      checking={checkQuery.isLoading || check.isPending || save.isPending}
      saving={save.isPending}
      saveError={save.error ? errorMessage(save.error) : null}
      onChange={(channel) => save.mutate(channel)}
      onCheck={() => check.mutate()}
      onRetry={() => {
        check.reset();
        void channelQuery.refetch();
        if (desktop) void checkQuery.refetch();
      }}
    />
  );
}

export function UpdateChannelView({
  loading,
  loadError,
  browserReason,
  channel,
  check,
  checking,
  saving,
  saveError,
  onChange,
  onCheck,
  onRetry,
}: UpdateChannelViewProps) {
  const locked = Boolean(browserReason) || saving;

  return (
    <Panel
      title="Update channel"
      subtitle="Which publications this installed app accepts as updates. Your data is not touched by updates."
      actions={
        channel && !browserReason ? (
          <Button size="xs" variant="secondary" loading={checking} onClick={onCheck}>
            Check now
          </Button>
        ) : null
      }
    >
      <div className="space-y-4">
        {loading ? <StateBanner variant="loading" title="Loading update channel..." size="dense" /> : null}
        {loadError ? (
          <StateBanner
            variant="error"
            title="Could not load update settings"
            message={loadError}
            size="dense"
            onRetry={onRetry}
          />
        ) : null}
        {browserReason ? <StateBanner variant="browser-only" message={browserReason} size="dense" /> : null}

        {channel ? (
          <fieldset disabled={locked} className="space-y-2">
            <legend className="sr-only">Update channel</legend>
            {CHANNEL_OPTIONS.map((option) => (
              <label
                key={option.value}
                className="flex cursor-pointer items-start gap-3 rounded border border-zinc-800 p-3 text-sm"
                style={channel === option.value ? { borderColor: "var(--color-action-primary)" } : undefined}
              >
                <input
                  type="radio"
                  name="update-channel"
                  value={option.value}
                  checked={channel === option.value}
                  disabled={locked}
                  onChange={() => onChange(option.value)}
                  className="mt-1"
                  style={{ accentColor: "var(--color-action-primary)" }}
                />
                <span>
                  <span className="font-medium text-zinc-100">{option.label}</span>
                  <span className="mt-0.5 block text-xs leading-5 text-zinc-400">{option.description}</span>
                </span>
              </label>
            ))}
            <p className="text-xs leading-5 text-zinc-500">
              Switching back to releases only never downgrades: the app keeps its version until a newer release is
              published.
              {saving ? " Saving..." : ""}
            </p>
          </fieldset>
        ) : null}
        {saveError ? (
          <StateBanner variant="error" title="Could not save the update channel" message={saveError} size="dense" />
        ) : null}

        {channel && check ? (
          <>
            <dl className="grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
              <Fact label="Current version" value={check.current_version ?? "unknown"} mono />
              <Fact label="Update status" value={checkLabel(check)} />
              <Fact label="Newest for this channel" value={newestLabel(check)} mono />
              <Fact label="Last check" value={check.checked_at ? formatDateTime(check.checked_at) : "Not checked yet"} />
            </dl>
            {check.status === "check_failed" ? (
              <StateBanner
                variant="warning"
                title="Update check failed"
                message="Could not reach GitHub Releases. The app keeps working with the installed version; check your connection and use Check now."
                size="dense"
              />
            ) : null}
            {check.status === "asset_missing" || check.status === "no_release" ? (
              <StateBanner variant="warning" title={checkLabel(check)} message={check.error ?? undefined} size="dense" />
            ) : null}
            {check.available ? (
              <p className="text-xs leading-5 text-zinc-400">
                Install it with Update in the top bar, or from{" "}
                <Link to="/settings/diagnostics" className="text-cyan-200 underline-offset-2 hover:underline">
                  Advanced &gt; Software update
                </Link>
                .
              </p>
            ) : null}
          </>
        ) : null}
      </div>
    </Panel>
  );
}

function Fact({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-wide text-zinc-500">{label}</dt>
      <dd className={`mt-1 break-words text-xs text-zinc-200 ${mono ? "font-mono" : ""}`}>{value}</dd>
    </div>
  );
}

function checkLabel(check: UpdateCheckResult): string {
  switch (check.status) {
    case "available":
      return "Update available";
    case "available_cached":
      return "Update available (found before the last failed check)";
    case "up_to_date":
      return "Up to date";
    case "check_failed":
      return "Update check failed";
    case "asset_missing":
      return "Publication package missing";
    case "no_release":
      return "No publication for this channel";
    case "snoozed":
      return "Update postponed";
    default:
      return "Not checked yet";
  }
}

function newestLabel(check: UpdateCheckResult): string {
  if (!check.latest_version) return "unknown";
  return check.publication_kind ? `${check.latest_version} (${check.publication_kind})` : check.latest_version;
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
