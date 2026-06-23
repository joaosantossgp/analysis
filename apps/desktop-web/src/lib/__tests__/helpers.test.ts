import { describe, it, expect, vi, beforeEach } from "vitest";
import { parseLayoutItems, resolveLayout, parseCardConfigs, type LayoutItem } from "../../routes/HomePage";
import { sanitizeFilename, escapeCsvCell } from "../../components/home/widgets/shared/csvExport";
import { resolveBridgeMode, resolveWidgetDataState, getBridgeBadgeStyles, getDataStateBadgeStyles } from "../bridge/badgeResolver";
import * as adapter from "../bridge/adapter";

// Mock adapter functions
vi.mock("../bridge/adapter", () => ({
  getBridgeMode: vi.fn(),
  whenBridgeReady: vi.fn().mockResolvedValue("desktop"),
  callBridge: vi.fn(),
}));

describe("Analyst Workspace Logic Helpers", () => {
  describe("Layout Parser and Collision Solver", () => {
    it("should parse valid layout items correctly and clamp coordinates", () => {
      const mockSaved = JSON.stringify([
        { id: "database-status", x: 5, y: 1, w: 4, h: 8, isMinimized: false, isCompact: false },
        { id: "watchlist", x: 1, y: 2, w: 2, h: 2, isMinimized: true, isCompact: true },
      ]);
      
      const parsed = parseLayoutItems(mockSaved);
      expect(parsed).toHaveLength(2);
      
      // database-status check: x should be clamped to (3-w), which is 0 since w=3 maximum.
      const dbStatus = parsed.find(x => x.id === "database-status");
      expect(dbStatus).toBeDefined();
      expect(dbStatus!.w).toBe(3); // w clamped to max 3
      expect(dbStatus!.h).toBe(6); // h clamped to max 6
      expect(dbStatus!.x).toBe(0); // x clamped to (3-3) = 0
      
      const watchlist = parsed.find(x => x.id === "watchlist");
      expect(watchlist).toBeDefined();
      expect(watchlist!.isMinimized).toBe(true);
      expect(watchlist!.isCompact).toBe(true);
    });

    it("should discard unknown card registry IDs", () => {
      const mockSaved = JSON.stringify([
        { id: "unknown-card-id-123", x: 0, y: 0, w: 1, h: 2 },
      ]);
      const parsed = parseLayoutItems(mockSaved);
      expect(parsed).toHaveLength(0);
    });

    it("should resolve layout collisions by pushing items downward", () => {
      const items: LayoutItem[] = [
        { id: "database-status", x: 0, y: 0, w: 3, h: 2, isMinimized: false, isCompact: false },
        { id: "watchlist", x: 0, y: 0, w: 2, h: 2, isMinimized: false, isCompact: false }, // collides with database-status
      ];
      
      const resolved = resolveLayout(items);
      const dbStatus = resolved.find(x => x.id === "database-status")!;
      const watchlist = resolved.find(x => x.id === "watchlist")!;
      
      expect(dbStatus.y).toBe(0);
      expect(watchlist.y).toBe(2); // Pushed down below database-status (height 2)
    });
  });

  describe("Card Configs Parser", () => {
    it("should return defaults if saved string is empty or invalid", () => {
      const parsedNull = parseCardConfigs(null);
      expect(parsedNull.watchlist).toBeDefined();
      expect(parsedNull.watchlist.metric).toBe("mg_ebit");
      
      const parsedInvalid = parseCardConfigs("invalid-json");
      expect(parsedInvalid.watchlist.metric).toBe("mg_ebit");
    });

    it("should merge saved config over default values", () => {
      const saved = JSON.stringify({
        watchlist: { companyIds: [{ cdCvm: 123, name: "Test" }], metric: "roe" }
      });
      const parsed = parseCardConfigs(saved);
      expect(parsed.watchlist.metric).toBe("roe");
      expect(parsed.watchlist.companyIds).toHaveLength(1);
      // Merged defaults should still exist
      expect(parsed["market-price"]).toBeDefined();
      expect(parsed["market-price"].cdCvm).toBe(0);
    });
  });

  describe("CSV Escaping and Sanitization", () => {
    it("should escape special characters in CSV cell formatting", () => {
      expect(escapeCsvCell(null)).toBe("");
      expect(escapeCsvCell(12.5)).toBe("12.5");
      expect(escapeCsvCell("Standard Text")).toBe("Standard Text");
      expect(escapeCsvCell('Text with "quotes"')).toBe('"Text with ""quotes"""');
      expect(escapeCsvCell("Text, with commas")).toBe('"Text, with commas"');
      expect(escapeCsvCell("Text\nwith newline")).toBe('"Text\nwith newline"');
    });

    it("should sanitize filenames to prevent path traversal and invalid characters", () => {
      expect(sanitizeFilename("company/..//report")).toBe("company_._report");
      expect(sanitizeFilename("company/report?id=123")).toBe("company_report_id_123");
      expect(sanitizeFilename("watchlist_PETR4-KPI.csv")).toBe("watchlist_PETR4-KPI.csv");
    });
  });

  describe("Runtime and Data-state Badge Resolver", () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it("should resolve bridge environment mode correctly", () => {
      vi.mocked(adapter.getBridgeMode).mockReturnValue("mock");
      expect(resolveBridgeMode()).toBe("mock");

      vi.mocked(adapter.getBridgeMode).mockReturnValue("browser");
      expect(resolveBridgeMode()).toBe("browser");

      vi.mocked(adapter.getBridgeMode).mockReturnValue("desktop");
      expect(resolveBridgeMode()).toBe("desktop");
    });

    it("should get bridge badge styles", () => {
      const mockStyles = getBridgeBadgeStyles("mock");
      expect(mockStyles.text).toBe("MOCK · FIXTURE");
      expect(mockStyles.className).toContain("text-purple-400");

      const browserStyles = getBridgeBadgeStyles("browser");
      expect(browserStyles.text).toBe("BROWSER · FALLBACK");
      expect(browserStyles.className).toContain("text-amber-400");

      const desktopStyles = getBridgeBadgeStyles("desktop");
      expect(desktopStyles.text).toBe("DESKTOP · LOCAL");
      expect(desktopStyles.className).toContain("text-emerald-400");
    });

    it("should resolve widget data readiness state based on queries status", () => {
      expect(resolveWidgetDataState({ isLoading: true, error: null, hasData: false })).toBe("loading");
      expect(resolveWidgetDataState({ isLoading: false, error: new Error("Fail"), hasData: false })).toBe("error");
      expect(resolveWidgetDataState({ isLoading: false, error: null, hasData: false })).toBe("empty");
      expect(resolveWidgetDataState({ isLoading: false, error: null, hasData: false, isOffline: true })).toBe("no_import");
      expect(resolveWidgetDataState({ isLoading: false, error: null, hasData: true, isStale: true })).toBe("stale");
      expect(resolveWidgetDataState({ isLoading: false, error: null, hasData: true, isStale: false })).toBe("ready");
    });

    it("should return correct data state badge style properties", () => {
      expect(getDataStateBadgeStyles("loading")!.text).toBe("LOADING");
      expect(getDataStateBadgeStyles("error")!.text).toBe("ERROR");
      expect(getDataStateBadgeStyles("no_import")!.text).toBe("NO IMPORT");
      expect(getDataStateBadgeStyles("stale")!.text).toBe("STALE");
      expect(getDataStateBadgeStyles("ready")!.text).toBe("READY");
    });
  });
});
