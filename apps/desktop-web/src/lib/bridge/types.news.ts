export interface NewsSource {
  source_id: string;
  name: string;
  source_type: string;
  reliability_layer: string;
  feed_url: string;
  homepage_url?: string | null;
  enabled: number | boolean;
  priority: number;
  user_defined: number | boolean;
  etag?: string | null;
  last_modified?: string | null;
  updated_at?: string | null;
  last_attempt_at?: string | null;
  last_success_at?: string | null;
  last_status?: string | null;
  last_error?: string | null;
  last_http_status?: number | null;
  consecutive_failures?: number | null;
  last_article_count?: number | null;
}

export interface NewsArticle {
  article_id: string;
  source_id: string;
  source_item_id?: string | null;
  title: string;
  source_name: string;
  original_url: string;
  canonical_url: string;
  published_at?: string | null;
  discovered_at: string;
  fetched_at?: string | null;
  summary?: string | null;
  language?: string | null;
  content_status: string;
  paywall_status?: string | null;
  read: number | boolean;
  saved: number | boolean;
  hidden: number | boolean;
  read_later: number | boolean;
  notes?: string | null;
  relevance_score?: number | null;
  priority_level?: "Normal" | "High" | "Critical" | string;
  relevance_components?: Record<string, number>;
  relevance_reasons?: string[];
}

export interface NewsArticleState {
  article_id: string;
  read: number | boolean;
  saved: number | boolean;
  hidden: number | boolean;
  read_later: number | boolean;
  notes?: string | null;
}

export interface UpdateNewsArticleStateParams {
  article_id: string;
  read?: boolean;
  saved?: boolean;
  hidden?: boolean;
  read_later?: boolean;
  notes?: string | null;
}

export interface UpdateNewsArticleStateResult {
  status: "success" | "error" | "not_found" | "blocked" | string;
  state?: NewsArticleState;
  error?: string;
}

export interface NewsArticlesParams {
  limit?: number;
  offset?: number;
  source_id?: string | null;
  include_hidden?: boolean;
  order?: "latest" | "top";
}

export interface NewsArticlesResponse {
  items: NewsArticle[];
  count: number;
  total: number;
  limit: number;
  offset: number;
  order?: "latest" | "top";
  error?: string;
}

export interface NewsOverviewParams {
  limit_per_section?: number;
}

export interface NewsOverviewSection {
  section_id: string;
  title: string;
  reason: string;
  items: NewsArticle[];
}

export interface NewsOverviewResponse {
  sections: NewsOverviewSection[];
  limit_per_section: number;
  error?: string;
}

export interface NewsCompanyScopeOverride {
  cd_cvm: number;
  action: "include" | "exclude" | string;
  reason?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface NewsCompanyScopeResponse {
  selected_preset?: string | null;
  coverage_count: number;
  included_count: number;
  excluded_count: number;
  overrides: NewsCompanyScopeOverride[];
  error?: string;
}

export interface SetNewsCompanyScopeOverrideParams {
  cd_cvm: number;
  action?: "include" | "exclude" | "" | null | string;
  reason?: string | null;
}

export interface SetNewsCompanyScopeOverrideResult {
  status: "success" | "error" | "blocked" | string;
  cd_cvm?: number;
  action?: "include" | "exclude" | null | string;
  deleted?: boolean;
  error?: string;
}

export interface NewsArticleKeywordMatch {
  keyword_rule_id: string;
  group_name: string;
  term: string;
  matched_term: string;
  match_method: string;
  match_reason: string;
  relevance_score?: number | null;
}

export interface NewsArticleTopicMatch {
  topic_id: string;
  label: string;
  topic_type: string;
  match_method: string;
  match_reason: string;
  relevance_score?: number | null;
}

export interface NewsArticleEventTypeMatch {
  event_type_id: string;
  category: string;
  sub_event?: string | null;
  match_method: string;
  match_reason: string;
  relevance_score?: number | null;
}

export interface NewsArticleCompanyMatch {
  cd_cvm: number;
  match_method: string;
  match_reason: string;
  relevance_score?: number | null;
  rule_strength?: number | null;
  is_primary: number | boolean;
  manually_reviewed: number | boolean;
}

export interface NewsArticleSectorMatch {
  sector_slug: string;
  sector_name: string;
  parent_sector_slug?: string | null;
  parent_sector_name?: string | null;
  match_method: string;
  match_reason: string;
  relevance_score?: number | null;
  rule_strength?: number | null;
  is_primary: number | boolean;
  manually_reviewed: number | boolean;
}

export interface NewsArticleClassificationResponse {
  keywords: NewsArticleKeywordMatch[];
  topics: NewsArticleTopicMatch[];
  event_types: NewsArticleEventTypeMatch[];
  companies: NewsArticleCompanyMatch[];
  sectors: NewsArticleSectorMatch[];
  corrections?: NewsClassificationCorrection[];
  score?: {
    total_score: number;
    priority_level: "Normal" | "High" | "Critical" | string;
    components: Record<string, number>;
    reasons: string[];
    updated_at?: string | null;
  } | null;
  error?: string;
}

export interface NewsClassificationCorrection {
  correction_id: string;
  article_id: string;
  target_type: string;
  target_id: string;
  original_value?: unknown;
  original_match_reason?: string | null;
  user_value?: Record<string, unknown>;
  correction_action: string;
  rule_suggestion?: string | null;
  created_at: string;
}

export interface ApplyNewsClassificationCorrectionParams {
  article_id: string;
  target_type: "company" | "sector" | "topic" | "event_type" | "keyword" | string;
  target_id: string;
  action: "add" | "remove" | string;
  user_value?: Record<string, unknown>;
  rule_suggestion?: string | null;
}

export interface ApplyNewsClassificationCorrectionResult {
  status: "success" | "error" | "not_found" | "blocked" | string;
  correction_id?: string;
  article_id?: string;
  target_type?: string;
  target_id?: string;
  correction_action?: string;
  error?: string;
}

export interface NewsSourcesResponse {
  items: NewsSource[];
  count: number;
  error?: string;
}

export interface NewsCollectionRun {
  run_id: string;
  trigger: string;
  status: string;
  started_at: string;
  finished_at?: string | null;
  source_count: number;
  articles_seen: number;
  articles_inserted: number;
  articles_updated: number;
  error_count: number;
  error_message?: string | null;
}

export interface NewsCollectionRunsResponse {
  items: NewsCollectionRun[];
  count: number;
  error?: string;
}

export interface NewsRefreshSourceResult {
  source_id: string;
  name: string;
  status: string;
  articles_seen: number;
  articles_inserted: number;
  articles_updated: number;
  error_count: number;
  error_message?: string | null;
}

export interface NewsRefreshStatus {
  status: "idle" | "running" | "success" | "error" | "started" | "already_running" | string;
  error?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  source_count?: number;
  completed_sources?: number;
  articles_seen?: number;
  articles_inserted?: number;
  articles_updated?: number;
  error_count?: number;
  sources?: NewsRefreshSourceResult[];
}

export interface NewsSourceMutationResult {
  status: "success" | "error" | "not_found" | "blocked" | string;
  source_id?: string;
  enabled?: boolean;
  priority?: number;
  error?: string;
}

export interface AddCustomNewsSourceParams {
  feed_url: string;
  name?: string;
  priority?: number;
  enabled?: boolean;
}

export interface AddCustomNewsSourceResult {
  status: "success" | "error" | "blocked" | string;
  source?: NewsSource | null;
  validation?: {
    title?: string | null;
    entry_count: number;
    http_status?: number | null;
    final_url?: string | null;
  };
  http_status?: number | null;
  final_url?: string | null;
  error?: string;
}
