import { callBridge, getBridgeMode, type BridgeMode } from "../bridge/adapter";
import type {
  AddCustomNewsSourceParams,
  AddCustomNewsSourceResult,
  ApplyNewsClassificationCorrectionParams,
  ApplyNewsClassificationCorrectionResult,
  NewsArticleClassificationResponse,
  NewsArticleContentResponse,
  NewsArticlesParams,
  NewsArticlesResponse,
  NewsCompanyScopeResponse,
  NewsCollectionRunsResponse,
  NewsOverviewParams,
  NewsOverviewResponse,
  NewsRefreshStatus,
  NewsRetentionStatus,
  NewsSourceMutationResult,
  NewsSourcesResponse,
  SaveNewsRetentionPolicyParams,
  SaveNewsRetentionPolicyResult,
  CleanupNewsExtractedContentResult,
  SetNewsCompanyScopeOverrideParams,
  SetNewsCompanyScopeOverrideResult,
  UpdateNewsArticleStateParams,
  UpdateNewsArticleStateResult,
  BridgeApi,
} from "../bridge/types";

const BROWSER_REASON =
  "News requires the desktop bridge or the local News dev bridge. Open CVMAnalytics through the desktop shell, or set VITE_NEWS_DEV_BRIDGE_URL in Vite dev mode.";

type NewsBridgeMode = BridgeMode | "dev-http";

const DEV_NEWS_BRIDGE_URL =
  import.meta.env.DEV === true ? String(import.meta.env.VITE_NEWS_DEV_BRIDGE_URL || "").replace(/\/+$/, "") : "";

function getNewsBridgeMode(): NewsBridgeMode {
  const mode = getBridgeMode();
  if (mode === "browser" && DEV_NEWS_BRIDGE_URL) return "dev-http";
  return mode;
}

async function callNewsBridge<K extends keyof BridgeApi>(
  method: K,
  params: Parameters<BridgeApi[K]>[0],
): Promise<Awaited<ReturnType<BridgeApi[K]>>> {
  if (getNewsBridgeMode() !== "dev-http") {
    return callBridge(method, params);
  }
  const response = await fetch(`${DEV_NEWS_BRIDGE_URL}/bridge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ method, params }),
  });
  if (!response.ok) {
    throw new Error(`News dev bridge returned HTTP ${response.status}`);
  }
  return (await response.json()) as Awaited<ReturnType<BridgeApi[K]>>;
}

export type NewsApiResult<T> =
  | ({ mode: "desktop" | "mock" | "dev-http" } & T)
  | ({ mode: "browser"; reason: string } & T);

export async function fetchNewsArticles(
  params: NewsArticlesParams = {},
): Promise<NewsApiResult<NewsArticlesResponse>> {
  const mode = getNewsBridgeMode();
  if (mode === "browser") {
    return {
      mode,
      reason: BROWSER_REASON,
      items: [],
      count: 0,
      total: 0,
      limit: params.limit ?? 50,
      offset: params.offset ?? 0,
    };
  }
  const payload = await callNewsBridge("get_news_articles", params);
  return { mode, ...payload };
}

export async function fetchNewsArticleClassification(
  articleId: string,
): Promise<NewsApiResult<NewsArticleClassificationResponse>> {
  const mode = getNewsBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, keywords: [], topics: [], event_types: [], companies: [], sectors: [], score: null };
  }
  const payload = await callNewsBridge("get_news_article_classification", { article_id: articleId });
  return { mode, ...payload };
}

export async function fetchNewsArticleContent(
  articleId: string,
): Promise<NewsApiResult<NewsArticleContentResponse>> {
  const mode = getNewsBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, available: false, error: BROWSER_REASON };
  }
  const payload = await callNewsBridge("get_news_article_content", { article_id: articleId });
  return { mode, ...payload };
}

export async function fetchNewsOverview(
  params: NewsOverviewParams = {},
): Promise<NewsApiResult<NewsOverviewResponse>> {
  const mode = getNewsBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, sections: [], limit_per_section: params.limit_per_section ?? 6 };
  }
  const payload = await callNewsBridge("get_news_overview", params);
  return { mode, ...payload };
}

export async function fetchNewsCompanyScope(): Promise<NewsApiResult<NewsCompanyScopeResponse>> {
  const mode = getNewsBridgeMode();
  if (mode === "browser") {
    return {
      mode,
      reason: BROWSER_REASON,
      selected_preset: null,
      coverage_count: 0,
      included_count: 0,
      excluded_count: 0,
      overrides: [],
    };
  }
  const payload = await callNewsBridge("get_news_company_scope", {});
  return { mode, ...payload };
}

export async function fetchNewsRetentionStatus(): Promise<NewsApiResult<NewsRetentionStatus>> {
  const mode = getNewsBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, content_count: 0, storage_bytes: 0, saved_content_count: 0 };
  }
  const payload = await callNewsBridge("get_news_retention_status", {});
  return { mode, ...payload };
}

export async function fetchNewsSources(): Promise<NewsApiResult<NewsSourcesResponse>> {
  const mode = getNewsBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, items: [], count: 0 };
  }
  const payload = await callNewsBridge("get_news_sources", {});
  return { mode, ...payload };
}

export async function fetchNewsCollectionRuns(
  limit = 20,
): Promise<NewsApiResult<NewsCollectionRunsResponse>> {
  const mode = getNewsBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, items: [], count: 0 };
  }
  const payload = await callNewsBridge("get_news_collection_runs", { limit });
  return { mode, ...payload };
}

export async function fetchNewsRefreshStatus(): Promise<NewsApiResult<NewsRefreshStatus>> {
  const mode = getNewsBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, status: "error", error: BROWSER_REASON };
  }
  const payload = await callNewsBridge("get_news_refresh_status", {});
  return { mode, ...payload };
}

export async function refreshNewsSources(): Promise<NewsApiResult<NewsRefreshStatus>> {
  const mode = getNewsBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, status: "error", error: BROWSER_REASON };
  }
  const payload = await callNewsBridge("refresh_news_sources", {});
  return { mode, ...payload };
}

export async function setNewsSourceEnabled(params: {
  source_id: string;
  enabled: boolean;
}): Promise<NewsApiResult<NewsSourceMutationResult>> {
  const mode = getNewsBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, status: "error", error: BROWSER_REASON };
  }
  const payload = await callNewsBridge("set_news_source_enabled", params);
  return { mode, ...payload };
}

export async function setNewsSourcePriority(params: {
  source_id: string;
  priority: number;
}): Promise<NewsApiResult<NewsSourceMutationResult>> {
  const mode = getNewsBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, status: "error", error: BROWSER_REASON };
  }
  const payload = await callNewsBridge("set_news_source_priority", params);
  return { mode, ...payload };
}

export async function addCustomNewsSource(
  params: AddCustomNewsSourceParams,
): Promise<NewsApiResult<AddCustomNewsSourceResult>> {
  const mode = getNewsBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, status: "error", error: BROWSER_REASON };
  }
  const payload = await callNewsBridge("add_custom_news_source", params);
  return { mode, ...payload };
}

export async function updateNewsArticleState(
  params: UpdateNewsArticleStateParams,
): Promise<NewsApiResult<UpdateNewsArticleStateResult>> {
  const mode = getNewsBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, status: "error", error: BROWSER_REASON };
  }
  const payload = await callNewsBridge("update_news_article_state", params);
  return { mode, ...payload };
}

export async function applyNewsClassificationCorrection(
  params: ApplyNewsClassificationCorrectionParams,
): Promise<NewsApiResult<ApplyNewsClassificationCorrectionResult>> {
  const mode = getNewsBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, status: "error", error: BROWSER_REASON };
  }
  const payload = await callNewsBridge("apply_news_classification_correction", params);
  return { mode, ...payload };
}

export async function setNewsCompanyScopeOverride(
  params: SetNewsCompanyScopeOverrideParams,
): Promise<NewsApiResult<SetNewsCompanyScopeOverrideResult>> {
  const mode = getNewsBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, status: "error", error: BROWSER_REASON };
  }
  const payload = await callNewsBridge("set_news_company_scope_override", params);
  return { mode, ...payload };
}

export async function saveNewsRetentionPolicy(
  params: SaveNewsRetentionPolicyParams,
): Promise<NewsApiResult<SaveNewsRetentionPolicyResult>> {
  const mode = getNewsBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, status: "error", error: BROWSER_REASON };
  }
  const payload = await callNewsBridge("save_news_retention_policy", params);
  return { mode, ...payload };
}

export async function cleanupNewsExtractedContent(
  params: { dry_run?: boolean } = {},
): Promise<NewsApiResult<CleanupNewsExtractedContentResult>> {
  const mode = getNewsBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, status: "error", error: BROWSER_REASON };
  }
  const payload = await callNewsBridge("cleanup_news_extracted_content", params);
  return { mode, ...payload };
}
