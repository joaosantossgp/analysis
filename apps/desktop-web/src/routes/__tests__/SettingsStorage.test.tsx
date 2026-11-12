import { renderToStaticMarkup } from "react-dom/server";
import {
  QueryClient,
  QueryClientProvider,
  type MutationObserver,
  type MutationObserverOptions,
} from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchStorageInventory, startStorageInventoryScan, type StorageInventoryResult } from "@/lib/api/storageInventory";
import type { SettingsHealthSummary, StartStorageInventoryScanResult, StorageInventory, StorageScanStatus } from "@/lib/bridge/types";
import { SettingsStorage } from "../SettingsModule";

const observers = vi.hoisted(() => new Map<unknown, MutationObserver<unknown, Error, unknown>>());

// SSR has no mounted hook lifecycle. Keep the real mutation observer across
// renders so the component's callbacks and query-cache transitions still run.
vi.mock("@tanstack/react-query", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-query")>();
  return {
    ...actual,
    useMutation(options: MutationObserverOptions<unknown, Error, unknown>) {
      const client = actual.useQueryClient();
      let observer = observers.get(options.mutationFn);
      if (!observer) {
        observer = new actual.MutationObserver(client, options);
        observers.set(options.mutationFn, observer);
      }
      observer.setOptions(options);
      return observer.getCurrentResult();
    },
  };
});

vi.mock("@/lib/api/storageInventory", () => ({
  fetchStorageInventory: vi.fn(),
  startStorageInventoryScan: vi.fn(),
}));

const key = ["storage-inventory"];
const summary: SettingsHealthSummary = {
  generated_at: "2026-01-01T00:00:00Z",
  overall_status: "healthy",
  summary: { title: "Local data", message: "Cached inventory" },
  segments: [], active_jobs: [], warnings: [], errors: [], provenance: [],
  storage: {},
  runtime: {
    version: "0.30.0-rc.1", runtime_mode: "vite", bridge_status: "ready",
    frozen: true, desktop_shell: "pywebview/WebView2", local_first: true,
  },
};

function inventory(scan_status: StorageScanStatus): StorageInventory {
  return {
    contract_version: 1,
    status: scan_status.status === "partial" ? "partial" : "healthy",
    generated_at: "2026-01-01T00:00:00Z",
    scanned_at: "2026-01-01T00:00:00Z",
    is_cached: true,
    is_stale: false,
    scan_age_seconds: 0,
    scan_status,
    logical_bytes_total: 4096,
    file_count: 3,
    directory_count: 1,
    skipped_count: 0,
    elapsed_ms: 84,
    roots: [], excluded_roots: [], volumes: [], categories: [], segments: [],
    databases: [], backup_candidates: [], largest_items: [],
    growth: { available: false }, warnings: [], errors: [], measurement_notes: [],
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

let client: QueryClient;

beforeEach(() => {
  client = new QueryClient({ defaultOptions: {
    queries: { retry: false, staleTime: Infinity, gcTime: Infinity },
    mutations: { retry: false, gcTime: Infinity },
  } });
  setInventory({ status: "idle" });
});

afterEach(() => {
  client.clear();
  observers.clear();
  vi.resetAllMocks();
});

function setInventory(status: StorageScanStatus) {
  client.setQueryData<StorageInventoryResult>(key, { mode: "desktop", inventory: inventory(status) });
}

function render(healthSummary = summary) {
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <SettingsStorage loading={false} summary={healthSummary} />
    </QueryClientProvider>,
  );
}

function refreshButton(markup = render()) {
  const button = markup.match(/<button\b[^>]*>[\s\S]*?<\/button>/g)
    ?.find((item) => /Refresh inventory|Scanning\.\.\./.test(item));
  expect(button).toBeDefined();
  return button!;
}

function start() {
  render();
  return observers.get(startStorageInventoryScan)!.mutate(undefined);
}

describe("Settings storage scan feedback", () => {
  it.each(["succeeded", "partial", "failed"] as const)("releases refresh after running becomes %s", async (status) => {
    vi.mocked(startStorageInventoryScan).mockResolvedValue({
      started: true, scan_status: { scan_id: "scan-1", status: "running" },
    });
    await start();
    expect(refreshButton()).toContain('disabled=""');
    expect(refreshButton()).toContain("Scanning...");

    setInventory({ scan_id: "scan-1", status, error: status === "failed" ? "Snapshot is locked" : null });
    expect(refreshButton()).not.toContain('disabled=""');
    expect(refreshButton()).toContain("Refresh inventory");
  });

  it("shows a worker failure alongside the last successful inventory", () => {
    setInventory({ scan_id: "scan-1", status: "failed", error: "Snapshot is locked" });
    const markup = render();
    expect(markup).toContain("Storage scan failed");
    expect(markup).toContain("Snapshot is locked");
    expect(markup).toContain("previous inventory");
    expect(markup).toContain("4.00 KiB");
    expect(refreshButton(markup)).not.toContain('disabled=""');
  });

  it("lets a retry replace the failed scan and finish normally", async () => {
    setInventory({ scan_id: "scan-1", status: "failed", error: "Snapshot is locked" });
    vi.mocked(startStorageInventoryScan).mockResolvedValue({
      started: true, scan_status: { scan_id: "scan-2", status: "running" },
    });
    await start();
    expect(refreshButton()).toContain("Scanning...");
    expect(render()).not.toContain("Snapshot is locked");
    setInventory({ scan_id: "scan-2", status: "succeeded" });
    expect(refreshButton()).not.toContain('disabled=""');
  });

  it("ignores a prior terminal query arriving while a new scan starts", async () => {
    const previous = { mode: "desktop", inventory: inventory({ scan_id: "scan-1", status: "succeeded" }) } satisfies StorageInventoryResult;
    client.setQueryData(key, previous);
    const staleRead = deferred<StorageInventoryResult>();
    vi.mocked(fetchStorageInventory).mockReturnValue(staleRead.promise);
    const oldRequest = client.fetchQuery({ queryKey: key, queryFn: fetchStorageInventory, staleTime: 0 }).catch(() => undefined);
    const admission = deferred<StartStorageInventoryScanResult>();
    vi.mocked(startStorageInventoryScan).mockReturnValue(admission.promise);
    const request = start();
    await vi.waitFor(() => expect(refreshButton()).toContain("Scanning..."));

    admission.resolve({ started: true, scan_status: { scan_id: "scan-2", status: "running" } });
    await request;
    staleRead.resolve(previous);
    await oldRequest;
    expect(refreshButton()).toContain('disabled=""');
    expect(client.getQueryData<StorageInventoryResult>(key)?.inventory.scan_status.scan_id).toBe("scan-2");

    setInventory({ scan_id: "scan-2", status: "succeeded" });
    expect(refreshButton()).not.toContain('disabled=""');
  });

  it("waits for the initial inventory before allowing a scan", () => {
    client.removeQueries({ queryKey: key });
    expect(refreshButton()).toContain('disabled=""');
  });

  it("keeps browser unavailability distinct from a failed worker scan", async () => {
    const facade = await vi.importActual<typeof import("@/lib/api/storageInventory")>("@/lib/api/storageInventory");
    const result = await facade.fetchStorageInventory();
    if (result.mode !== "browser") throw new Error("Expected the bridge-free browser result");
    client.setQueryData(key, result);
    const markup = render({ ...summary, runtime: { ...summary.runtime, bridge_status: "unknown" } });

    expect(markup).toContain(result.reason);
    expect(refreshButton(markup)).toContain('disabled=""');
    expect(markup).not.toContain("Storage scan failed");
  });
});
