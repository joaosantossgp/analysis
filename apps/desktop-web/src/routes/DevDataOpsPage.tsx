import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../components/ui/Button";
import {
  devGetRawState,
  devResetJobs,
  devResetUniverse,
  devSimulateRefresh,
  devStartSmallSetup,
  type DevSimulateMode,
} from "../lib/api/devTools";

// Gate: must be a Vite dev build AND the flag must be set in localStorage.
// Read on render: the dev panel sets the flag right before navigating here.
const isAllowed = () =>
  import.meta.env.DEV &&
  typeof window !== "undefined" &&
  window.localStorage?.getItem("cvm_dev_tools") === "1";

// ─── Gate screen ─────────────────────────────────────────────────────────────

function Blocked() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 text-zinc-400">
      <div className="max-w-sm space-y-3 text-center">
        <p className="text-sm font-mono">404 — not found</p>
        <p className="text-xs text-zinc-600">
          (dev tools require a DEV build and{" "}
          <code className="font-mono text-zinc-500">
            localStorage.cvm_dev_tools = &apos;1&apos;
          </code>
          )
        </p>
      </div>
    </div>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-500">{title}</h2>
      {children}
    </section>
  );
}

function StatusLine({ label, ok, msg }: { label: string; ok?: boolean; msg?: string }) {
  const colour = ok === undefined ? "text-zinc-500" : ok ? "text-green-400" : "text-red-400";
  return (
    <p className={`text-xs font-mono ${colour}`}>
      {label}: {msg ?? (ok ? "ok" : "error")}
    </p>
  );
}

// ─── Reset panel ─────────────────────────────────────────────────────────────

function ResetPanel() {
  const qc = useQueryClient();
  const [results, setResults] = useState<Record<string, string>>({});

  function makeReset(key: string, fn: () => Promise<void>) {
    return async () => {
      try {
        await fn();
        setResults((r) => ({ ...r, [key]: "ok" }));
        qc.invalidateQueries();
      } catch (e) {
        setResults((r) => ({ ...r, [key]: String(e) }));
      }
    };
  }

  return (
    <Section title="Reset controls">
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="danger" onClick={makeReset("universe", devResetUniverse)}>
          Reset universe
        </Button>
        <Button size="sm" variant="danger" onClick={makeReset("jobs", devResetJobs)}>
          Reset jobs
        </Button>
        <Button
          size="sm"
          variant="danger"
          onClick={makeReset("all", async () => {
            await devResetUniverse();
            await devResetJobs();
          })}
        >
          Reset all
        </Button>
      </div>
      <div className="space-y-1">
        {Object.entries(results).map(([k, v]) => (
          <StatusLine key={k} label={k} ok={v === "ok"} msg={v} />
        ))}
      </div>
    </Section>
  );
}

// ─── Simulation panel ─────────────────────────────────────────────────────────

const SIM_MODES: Array<{ mode: DevSimulateMode; label: string; description: string }> = [
  { mode: "success", label: "Success", description: "Instant terminal success job" },
  { mode: "partial", label: "Partial", description: "One success + one error job" },
  { mode: "fail", label: "Fail", description: "Instant terminal error job" },
  { mode: "slow", label: "Slow (~14s)", description: "Job progresses through all stages" },
];

function SimulationPanel() {
  const qc = useQueryClient();
  const [lastResult, setLastResult] = useState<string | null>(null);
  const [running, setRunning] = useState<DevSimulateMode | null>(null);

  async function run(mode: DevSimulateMode) {
    setRunning(mode);
    setLastResult(null);
    try {
      const jobId = await devSimulateRefresh(mode);
      setLastResult(`ok — job_id: ${jobId ?? "n/a"}`);
      qc.invalidateQueries({ queryKey: ["refresh-jobs"] });
    } catch (e) {
      setLastResult(`error: ${String(e)}`);
    } finally {
      setRunning(null);
    }
  }

  return (
    <Section title="Mock simulation">
      <div className="flex flex-wrap gap-2">
        {SIM_MODES.map(({ mode, label, description }) => (
          <button
            key={mode}
            title={description}
            disabled={running !== null}
            onClick={() => run(mode)}
            className="rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-200 hover:border-zinc-500 disabled:opacity-40"
          >
            {running === mode ? "…" : label}
          </button>
        ))}
      </div>
      {lastResult && (
        <p className={`text-xs font-mono ${lastResult.startsWith("ok") ? "text-green-400" : "text-red-400"}`}>
          {lastResult}
        </p>
      )}
    </Section>
  );
}

// ─── Small real setup ─────────────────────────────────────────────────────────

function SmallSetupPanel() {
  const qc = useQueryClient();
  const [count, setCount] = useState(5);
  const [result, setResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setResult(null);
    try {
      await devStartSmallSetup(count);
      setResult("started");
      qc.invalidateQueries({ queryKey: ["refresh-jobs"] });
    } catch (e) {
      setResult(`error: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section title="Small real-universe setup">
      <p className="text-xs text-zinc-500">
        Runs <code>request_refresh(mode=missing)</code> against the first N companies already in the local DB.
        No external API calls.
      </p>
      <div className="flex items-center gap-3">
        <label className="text-xs text-zinc-400">
          Companies:
          <input
            type="number"
            min={1}
            max={10}
            value={count}
            onChange={(e) => setCount(Math.max(1, Math.min(10, Number(e.target.value))))}
            className="ml-2 w-14 rounded border border-zinc-700 bg-zinc-800 px-2 py-0.5 text-xs text-zinc-200"
          />
        </label>
        <Button size="sm" disabled={busy} onClick={run}>
          {busy ? "Starting…" : "Start small setup"}
        </Button>
      </div>
      {result && (
        <p className={`text-xs font-mono ${result === "started" ? "text-green-400" : "text-red-400"}`}>
          {result}
        </p>
      )}
    </Section>
  );
}

// ─── Job inspector ────────────────────────────────────────────────────────────

function JobInspector() {
  const rawQuery = useQuery({
    queryKey: ["dev-raw-state"],
    queryFn: devGetRawState,
    refetchInterval: 2000,
  });

  const data = rawQuery.data;

  return (
    <Section title="Job inspector (2s refresh)">
      {rawQuery.isError && (
        <p className="text-xs text-red-400 font-mono">{String(rawQuery.error)}</p>
      )}

      <div className="space-y-2">
        <p className="text-xs font-semibold text-zinc-400">app_settings</p>
        {data?.app_settings?.length ? (
          <table className="w-full text-xs font-mono">
            <tbody>
              {data.app_settings.map((r) => (
                <tr key={r.key} className="border-b border-zinc-800">
                  <td className="py-0.5 pr-4 text-zinc-500">{r.key}</td>
                  <td className="py-0.5 text-zinc-200 break-all">{r.value ?? "null"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-xs text-zinc-600">No settings rows.</p>
        )}
      </div>

      <div className="mt-3 space-y-2">
        <p className="text-xs font-semibold text-zinc-400">refresh_jobs (last 30)</p>
        {data?.refresh_jobs?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="text-left text-zinc-600">
                  <th className="pr-3 pb-1">state</th>
                  <th className="pr-3 pb-1">stage</th>
                  <th className="pr-3 pb-1">cd_cvm</th>
                  <th className="pr-3 pb-1">progress</th>
                  <th className="pr-3 pb-1">error</th>
                  <th className="pb-1">requested_at</th>
                </tr>
              </thead>
              <tbody>
                {data.refresh_jobs.map((j) => {
                  const state = String(j.state ?? "");
                  const stateColour =
                    state === "success"
                      ? "text-green-400"
                      : state === "error"
                        ? "text-red-400"
                        : state === "running"
                          ? "text-amber-400"
                          : "text-zinc-300";
                  return (
                    <tr key={String(j.id)} className="border-b border-zinc-800/60">
                      <td className={`py-0.5 pr-3 ${stateColour}`}>{state}</td>
                      <td className="py-0.5 pr-3 text-zinc-400">{String(j.stage ?? "—")}</td>
                      <td className="py-0.5 pr-3 text-zinc-300">{String(j.cd_cvm ?? "")}</td>
                      <td className="py-0.5 pr-3 text-zinc-400">
                        {j.progress_current != null
                          ? `${j.progress_current}/${j.progress_total}`
                          : "—"}
                      </td>
                      <td className="py-0.5 pr-3 max-w-[200px] truncate text-red-400">
                        {String(j.error_message ?? "")}
                      </td>
                      <td className="py-0.5 text-zinc-600">{String(j.requested_at ?? "")}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-xs text-zinc-600">No job rows.</p>
        )}
      </div>
    </Section>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function DevDataOpsPage() {
  if (!isAllowed()) return <Blocked />;

  return (
    <div className="mx-auto max-w-4xl space-y-5 px-5 py-8">
      <header className="space-y-1">
        <h1 className="text-base font-semibold text-zinc-100">Data Ops Dev Tools</h1>
        <p className="text-xs text-zinc-500">
          DEV build only. Not accessible in production builds.{" "}
          <code className="font-mono">localStorage.cvm_dev_tools=1</code>
        </p>
      </header>

      <ResetPanel />
      <SimulationPanel />
      <SmallSetupPanel />
      <JobInspector />
    </div>
  );
}
