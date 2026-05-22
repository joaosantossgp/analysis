import { useEffect, useState } from "react";

import { fetchHealth, type HealthResult } from "@/lib/api/health";
import { whenBridgeReady, type BridgeMode } from "@/lib/bridge/adapter";
import { PageHeader } from "@/components/PageHeader";

type LoadState =
  | { kind: "idle" }
  | { kind: "loading"; mode: BridgeMode }
  | { kind: "ok"; result: HealthResult }
  | { kind: "error"; message: string };

export function HealthCard() {
  const [state, setState] = useState<LoadState>({ kind: "idle" });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const mode = await whenBridgeReady();
      if (cancelled) return;
      setState({ kind: "loading", mode });
      try {
        const result = await fetchHealth();
        if (cancelled) return;
        setState({ kind: "ok", result });
      } catch (err) {
        if (cancelled) return;
        setState({
          kind: "error",
          message: err instanceof Error ? err.message : String(err),
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg space-y-4">
      <PageHeader
        title="Runtime health"
        subtitle="via pywebview bridge"
      />
      <Body state={state} />
    </section>
  );
}

function Body({ state }: { state: LoadState }) {
  if (state.kind === "idle" || state.kind === "loading") {
    return (
      <p className="text-sm text-zinc-400">
        {state.kind === "loading" ? `Connecting (${state.mode})…` : "Initialising…"}
      </p>
    );
  }
  if (state.kind === "error") {
    return (
      <p className="text-sm text-rose-400" role="alert">
        Error: {state.message}
      </p>
    );
  }
  const { result } = state;
  if (result.mode === "browser") {
    return (
      <div className="space-y-2 text-sm">
        <p className="text-amber-300">Browser-mode preview</p>
        <p className="text-zinc-400">{result.reason}</p>
      </div>
    );
  }
  const { payload } = result;
  return (
    <dl className="grid grid-cols-2 gap-3 text-sm">
      <dt className="text-zinc-500">Status</dt>
      <dd className={payload.status === "ok" ? "text-emerald-400" : "text-amber-400"}>
        {payload.status}
      </dd>
      <dt className="text-zinc-500">Version</dt>
      <dd className="font-mono text-zinc-200">{payload.version}</dd>
      <dt className="text-zinc-500">Database</dt>
      <dd className="font-mono text-zinc-200">
        {payload.database_dialect ?? "(unknown)"}
      </dd>
      <dt className="text-zinc-500">Warnings</dt>
      <dd className="text-zinc-200">{payload.warnings.length}</dd>
      <dt className="text-zinc-500">Errors</dt>
      <dd className={payload.errors.length === 0 ? "text-zinc-200" : "text-rose-400"}>
        {payload.errors.length}
      </dd>
    </dl>
  );
}
