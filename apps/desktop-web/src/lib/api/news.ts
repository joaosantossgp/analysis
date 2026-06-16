import { callBridge, getBridgeMode, type BridgeMode } from "../bridge/adapter";
import type {
  AddCustomNewsSourceParams,
  AddCustomNewsSourceResult,
  ApplyNewsClassificationCorrectionParams,
  ApplyNewsClassificationCorrectionResult,
  NewsArticleClassificationResponse,
  NewsArticlesParams,
  NewsArticlesResponse,
  NewsCompanyScopeResponse,
  NewsCollectionRunsResponse,
  NewsOverviewParams,
  NewsOverviewResponse,
  NewsRefreshStatus,
  NewsSourceMutationResult,
  NewsSourcesResponse,
  SetNewsCompanyScopeOverrideParams,
  SetNewsCompanyScopeOverrideResult,
  UpdateNewsArticleStateParams,
  UpdateNewsArticleStateResult,
} from "../bridge/types";

const BROWSER_REASON =
  "News requires the desktop bridge and local news database. Open CVMAnalytics through the desktop shell to use News.";

export type NewsApiResult<T> =
  | ({ mode: "desktop" | "mock" } & T)
  | ({ mode: "browser"; reason: string } & T);

export async function fetchNewsArticles(
  params: NewsArticlesParams = {},
): Promise<NewsApiResult<NewsArticlesResponse>> {
  const mode: BridgeMode = getBridgeMode();
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
  const payload = await callBridge("get_news_articles", params);
  return { mode, ...payload };
}

export async function fetchNewsArticleClassification(
  articleId: string,
): Promise<NewsApiResult<NewsArticleClassificationResponse>> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, keywords: [], topics: [], event_types: [], companies: [], sectors: [], score: null };
  }
  const payload = await callBridge("get_news_article_classification", { article_id: articleId });
  return { mode, ...payload };
}

export async function fetchNewsOverview(
  params: NewsOverviewParams = {},
): Promise<NewsApiResult<NewsOverviewResponse>> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, sections: [], limit_per_section: params.limit_per_section ?? 6 };
  }
  const payload = await callBridge("get_news_overview", params);
  return { mode, ...payload };
}

export async function fetchNewsCompanyScope(): Promise<NewsApiResult<NewsCompanyScopeResponse>> {
  const mode: BridgeMode = getBridgeMode();
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
  const payload = await callBridge("get_news_company_scope", {});
  return { mode, ...payload };
}

export async function fetchNewsSources(): Promise<NewsApiResult<NewsSourcesResponse>> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, items: [], count: 0 };
  }
  const payload = await callBridge("get_news_sources", {});
  return { mode, ...payload };
}

export async function fetchNewsCollectionRuns(
  limit = 20,
): Promise<NewsApiResult<NewsCollectionRunsResponse>> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, items: [], count: 0 };
  }
  const payload = await callBridge("get_news_collection_runs", { limit });
  return { mode, ...payload };
}

export async function fetchNewsRefreshStatus(): Promise<NewsApiResult<NewsRefreshStatus>> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, status: "error", error: BROWSER_REASON };
  }
  const payload = await callBridge("get_news_refresh_status", {});
  return { mode, ...payload };
}

export async function refreshNewsSources(): Promise<NewsApiResult<NewsRefreshStatus>> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, status: "error", error: BROWSER_REASON };
  }
  const payload = await callBridge("refresh_news_sources", {});
  return { mode, ...payload };
}

export async function setNewsSourceEnabled(params: {
  source_id: string;
  enabled: boolean;
}): Promise<NewsApiResult<NewsSourceMutationResult>> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, status: "error", error: BROWSER_REASON };
  }
  const payload = await callBridge("set_news_source_enabled", params);
  return { mode, ...payload };
}

export async function setNewsSourcePriority(params: {
  source_id: string;
  priority: number;
}): Promise<NewsApiResult<NewsSourceMutationResult>> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, status: "error", error: BROWSER_REASON };
  }
  const payload = await callBridge("set_news_source_priority", params);
  return { mode, ...payload };
}

export async function addCustomNewsSource(
  params: AddCustomNewsSourceParams,
): Promise<NewsApiResult<AddCustomNewsSourceResult>> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, status: "error", error: BROWSER_REASON };
  }
  const payload = await callBridge("add_custom_news_source", params);
  return { mode, ...payload };
}

export async function updateNewsArticleState(
  params: UpdateNewsArticleStateParams,
): Promise<NewsApiResult<UpdateNewsArticleStateResult>> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, status: "error", error: BROWSER_REASON };
  }
  const payload = await callBridge("update_news_article_state", params);
  return { mode, ...payload };
}

export async function applyNewsClassificationCorrection(
  params: ApplyNewsClassificationCorrectionParams,
): Promise<NewsApiResult<ApplyNewsClassificationCorrectionResult>> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, status: "error", error: BROWSER_REASON };
  }
  const payload = await callBridge("apply_news_classification_correction", params);
  return { mode, ...payload };
}

export async function setNewsCompanyScopeOverride(
  params: SetNewsCompanyScopeOverrideParams,
): Promise<NewsApiResult<SetNewsCompanyScopeOverrideResult>> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode, reason: BROWSER_REASON, status: "error", error: BROWSER_REASON };
  }
  const payload = await callBridge("set_news_company_scope_override", params);
  return { mode, ...payload };
}
