import { callBridge, getBridgeMode } from "../bridge/adapter";
import type {
  StartStorageInventoryScanResult,
  StorageInventory,
  StorageScanStatus,
} from "../bridge/types";

const BROWSER_REASON =
  "Storage inventory requires the desktop bridge. Open CVMAnalytics through the desktop shell to measure local data files.";

export type StorageInventoryResult =
  | { mode: "desktop" | "mock"; inventory: StorageInventory }
  | { mode: "browser"; inventory: StorageInventory; reason: string };

export async function fetchStorageInventory(): Promise<StorageInventoryResult> {
  const mode = getBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, inventory: browserStorageInventory() };
  }
  const inventory = await callBridge("get_storage_inventory", {});
  return { mode, inventory };
}

export async function startStorageInventoryScan(): Promise<StartStorageInventoryScanResult> {
  const mode = getBridgeMode();
  if (mode === "browser") {
    return {
      started: false,
      error: BROWSER_REASON,
      scan_status: { status: "failed", error: BROWSER_REASON },
    };
  }
  return callBridge("start_storage_inventory_scan", {});
}

export async function fetchStorageInventoryScanStatus(): Promise<StorageScanStatus> {
  const mode = getBridgeMode();
  if (mode === "browser") {
    return { status: "failed", error: BROWSER_REASON };
  }
  return callBridge("get_storage_inventory_scan_status", {});
}

function browserStorageInventory(): StorageInventory {
  return {
    contract_version: 1,
    status: "unavailable",
    generated_at: new Date().toISOString(),
    scanned_at: null,
    is_cached: true,
    is_stale: true,
    scan_age_seconds: null,
    scan_status: { status: "failed", error: BROWSER_REASON },
    logical_bytes_total: 0,
    allocated_bytes_total: null,
    file_count: 0,
    directory_count: 0,
    skipped_count: 0,
    elapsed_ms: null,
    roots: [],
    excluded_roots: [],
    volumes: [],
    categories: [],
    segments: [],
    databases: [],
    largest_items: [],
    growth: { available: false, reason: BROWSER_REASON },
    warnings: [],
    errors: [BROWSER_REASON],
    measurement_notes: [BROWSER_REASON],
  };
}
