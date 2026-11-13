import { expect, it, vi, afterEach } from "vitest";
import { callBridge, whenBridgeReady } from "../bridge/adapter";
import { fetchCoverageUniverses } from "./coverage";
vi.mock("../bridge/adapter", () => ({ callBridge: vi.fn(), whenBridgeReady: vi.fn(), getBridgeMode: vi.fn() }));
afterEach(() => vi.resetAllMocks());
it("rejects an unavailable bridge instead of caching an empty universe catalog", async () => {
  vi.mocked(whenBridgeReady).mockResolvedValue("browser");
  await expect(fetchCoverageUniverses()).rejects.toThrow("saved universe selection is preserved");
  expect(callBridge).not.toHaveBeenCalled();
});
it("waits for the bridge before reading the saved catalog", async () => {
  let ready!: (mode: "desktop") => void;
  vi.mocked(whenBridgeReady).mockReturnValue(new Promise(resolve => { ready = resolve; }));
  vi.mocked(callBridge).mockResolvedValue([{id: "saved-universe"}] as never);
  const request = fetchCoverageUniverses();
  expect(callBridge).not.toHaveBeenCalled();
  ready("desktop");
  await expect(request).resolves.toEqual([{id: "saved-universe"}]);
  expect(callBridge).toHaveBeenCalledWith("get_coverage_universes", {});
});
