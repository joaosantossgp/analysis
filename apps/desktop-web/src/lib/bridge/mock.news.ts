import type {
  BridgeApi,
} from "./types";
import { NOW } from "./mock.fixtures";

export function createMockNewsMethods(): Partial<BridgeApi> {
  return {
    get_news_articles: async (params) => {
      const limit = Number(params?.limit ?? 50);
      const offset = Number(params?.offset ?? 0);
      const order = params?.order === "top" ? "top" : "latest";
      const items = [
        {
          article_id: "mock-news-1",
          source_id: "bcb-rss",
          source_item_id: "mock-bcb-1",
          title: "Banco Central updates market expectations bulletin",
          source_name: "Banco Central do Brasil",
          original_url: "https://www.bcb.gov.br/mock/news-1",
          canonical_url: "https://www.bcb.gov.br/mock/news-1",
          published_at: NOW,
          discovered_at: NOW,
          fetched_at: NOW,
          summary: "Mock local news item for the future News overview.",
          language: "en",
          content_status: "summary_available",
          paywall_status: null,
          read: 0,
          saved: 0,
          hidden: 0,
          read_later: 0,
          notes: null,
          relevance_score: 3.25,
          priority_level: "High",
          relevance_components: {
            source_reliability: 1,
            freshness: 0.8,
            keyword_relevance: 0.7,
            company_relevance: 0.75,
          },
          relevance_reasons: [
            "Source reliability component 1.00 from official",
            "Priority set to High by deterministic score rules",
          ],
        },
      ].slice(offset, offset + limit);
      return { items, count: items.length, total: 1, limit, offset, order };
    },

    get_news_overview: async (params) => {
      const limit = Number(params?.limit_per_section ?? 6);
      const item = {
        article_id: "mock-news-1",
        source_id: "bcb-rss",
        source_item_id: "mock-bcb-1",
        title: "Banco Central updates market expectations bulletin",
        source_name: "Banco Central do Brasil",
        original_url: "https://www.bcb.gov.br/mock/news-1",
        canonical_url: "https://www.bcb.gov.br/mock/news-1",
        published_at: NOW,
        discovered_at: NOW,
        fetched_at: NOW,
        summary: "Mock local news item for the News overview.",
        language: "en",
        content_status: "summary_available",
        paywall_status: null,
        read: 0,
        saved: 0,
        hidden: 0,
        read_later: 0,
        notes: null,
        relevance_score: 3.25,
        priority_level: "High",
        relevance_components: {
          source_reliability: 1,
          freshness: 0.8,
          keyword_relevance: 0.7,
          company_relevance: 0.75,
        },
        relevance_reasons: [
          "Source reliability component 1.00 from official",
          "Priority set to High by deterministic score rules",
        ],
      };
      const sections = [
        ["critical_news", "Critical News", "Articles with Critical priority from deterministic scoring.", []],
        ["top_market_news", "Top Market News", "Highest ranked local articles using explainable score components.", [item]],
        ["macro_watch", "Macro Watch", "Articles matched to macro topics or macro keyword rules.", [item]],
        ["my_companies", "My Companies", "Articles with deterministic company associations.", [item]],
        ["my_sectors", "My Sectors", "Articles with deterministic sector associations.", [item]],
        ["keyword_alerts", "Keyword Alerts", "Articles matched to active keyword rules.", [item]],
        ["all_news", "All News", "Most recent local articles, without ranking.", [item]],
      ].map(([section_id, title, reason, items]) => ({
        section_id: String(section_id),
        title: String(title),
        reason: String(reason),
        items: (items as typeof item[]).slice(0, limit),
      }));
      return { sections, limit_per_section: limit };
    },

    get_news_company_scope: async () => ({
      selected_preset: "top_200",
      coverage_count: 200,
      included_count: 201,
      excluded_count: 0,
      overrides: [
        {
          cd_cvm: 9512,
          action: "include",
          reason: "Mock News-specific inclusion",
          created_at: NOW,
          updated_at: NOW,
        },
      ],
    }),

    get_news_article_classification: async () => ({
      keywords: [
        {
          keyword_rule_id: "kw_macro_selic",
          group_name: "Macro",
          term: "Selic",
          matched_term: "Selic",
          match_method: "keyword_exact",
          match_reason: "Matched keyword rule kw_macro_selic term 'Selic' in summary",
          relevance_score: 0.7,
        },
      ],
      topics: [
        {
          topic_id: "topic_macro_rates",
          label: "Interest rates",
          topic_type: "macro",
          match_method: "keyword_rule",
          match_reason: "Matched keyword rule kw_macro_selic term 'Selic' in summary",
          relevance_score: 0.7,
        },
      ],
      event_types: [],
      companies: [
        {
          cd_cvm: 9512,
          match_method: "ticker",
          match_reason: "Matched company CVM 9512 by ticker 'PETR4' in title",
          relevance_score: 1,
          rule_strength: 1,
          is_primary: 1,
          manually_reviewed: 0,
        },
      ],
      sectors: [
        {
          sector_slug: "energy",
          sector_name: "Energy",
          parent_sector_slug: null,
          parent_sector_name: null,
          match_method: "company_sector",
          match_reason: "Matched sector from company CVM 9512: matched ticker PETR4",
          relevance_score: 0.8,
          rule_strength: 1,
          is_primary: 1,
          manually_reviewed: 0,
        },
        {
          sector_slug: "integrated-oil-gas",
          sector_name: "Integrated Oil & Gas",
          parent_sector_slug: "energy",
          parent_sector_name: "Energy",
          match_method: "company_sub_industry",
          match_reason: "Matched sector from company CVM 9512: matched ticker PETR4",
          relevance_score: 0.85,
          rule_strength: 1,
          is_primary: 1,
          manually_reviewed: 0,
        },
      ],
      score: {
        total_score: 3.25,
        priority_level: "High",
        components: {
          source_reliability: 1,
          freshness: 0.8,
          keyword_relevance: 0.7,
          company_relevance: 0.75,
        },
        reasons: [
          "Source reliability component 1.00 from official",
          "Priority set to High by deterministic score rules",
        ],
        updated_at: NOW,
      },
      corrections: [],
    }),

    get_news_article_content: async (params) => ({
      article_id: params.article_id,
      title: "Banco Central updates market expectations bulletin",
      content_status: "full_text_available",
      paywall_status: null,
      available: true,
      content_text: "Mock locally stored feed content for the selected News article.",
      content_format: "feed",
      source_policy: "feed_content_allowed",
      storage_bytes: 64,
      extracted_at: NOW,
      updated_at: NOW,
    }),

    apply_news_classification_correction: async (params) => ({
      status: "success",
      correction_id: "mock-correction-1",
      article_id: params.article_id,
      target_type: params.target_type,
      target_id: params.target_id,
      correction_action: params.action,
    }),

    set_news_company_scope_override: async (params) => ({
      status: "success",
      cd_cvm: params.cd_cvm,
      action: params.action || null,
      deleted: !params.action,
    }),

    get_news_retention_status: async () => ({
      content_count: 0,
      storage_bytes: 0,
      saved_content_count: 0,
      oldest_extracted_at: null,
      newest_extracted_at: null,
      policy: {
        policy_id: "default",
        metadata_retention_days: 1825,
        extracted_text_retention_days: 90,
        total_storage_limit_mb: 512,
        preserve_saved: 1,
        preserve_official_documents: 1,
        updated_at: NOW,
      },
    }),

    save_news_retention_policy: async (params) => ({
      status: "success",
      policy: {
        policy_id: "default",
        metadata_retention_days: params.metadata_retention_days ?? 1825,
        extracted_text_retention_days: params.extracted_text_retention_days ?? 90,
        total_storage_limit_mb: params.total_storage_limit_mb ?? 512,
        preserve_saved: params.preserve_saved ?? true,
        preserve_official_documents: params.preserve_official_documents ?? true,
        updated_at: NOW,
      },
    }),

    cleanup_news_extracted_content: async (params) => ({
      status: "success",
      dry_run: Boolean(params?.dry_run),
      deleted_content_count: 0,
      freed_bytes: 0,
      preserved_saved: true,
      preserved_official_documents: true,
    }),

    backfill_news_article_content: async (params) => ({
      status: "success",
      limit: params?.limit ?? 25,
      include_normal: Boolean(params?.include_normal),
      candidate_count: 0,
      attempted_count: 0,
      stored_count: 0,
      paywalled_count: 0,
      failed_count: 0,
      skipped_count: 0,
      errors: [],
    }),

    get_news_sources: async () => ({
      items: [
        {
          source_id: "bcb-rss",
          name: "Banco Central do Brasil",
          source_type: "official",
          reliability_layer: "official",
          feed_url: "https://www.bcb.gov.br/acessoinformacao/rss",
          homepage_url: "https://www.bcb.gov.br/",
          enabled: 1,
          priority: 10,
          user_defined: 0,
          allow_content_storage: 1,
          etag: null,
          last_modified: null,
          updated_at: NOW,
          last_attempt_at: NOW,
          last_success_at: NOW,
          last_status: "success",
          last_error: null,
          last_http_status: 200,
          consecutive_failures: 0,
          last_article_count: 1,
        },
        {
          source_id: "b3-rss-news",
          name: "B3 RSS News",
          source_type: "official",
          reliability_layer: "official",
          feed_url: "https://www.b3.com.br/data/rss/suporteanegociacao.xml",
          homepage_url: "https://www.b3.com.br/",
          enabled: 1,
          priority: 20,
          user_defined: 0,
          allow_content_storage: 1,
          etag: null,
          last_modified: null,
          updated_at: NOW,
          last_attempt_at: null,
          last_success_at: null,
          last_status: null,
          last_error: null,
          last_http_status: null,
          consecutive_failures: 0,
          last_article_count: 0,
        },
      ],
      count: 2,
    }),

    get_news_collection_runs: async () => ({
      items: [
        {
          run_id: "mock-news-run-1",
          trigger: "manual",
          status: "success",
          started_at: NOW,
          finished_at: NOW,
          source_count: 2,
          articles_seen: 1,
          articles_inserted: 1,
          articles_updated: 0,
          error_count: 0,
          error_message: null,
        },
      ],
      count: 1,
    }),

    get_news_refresh_status: async () => ({
      status: "idle",
      error: null,
      started_at: null,
      finished_at: NOW,
      source_count: 2,
      completed_sources: 2,
      articles_seen: 1,
      articles_inserted: 1,
      articles_updated: 0,
      error_count: 0,
      sources: [],
    }),

    refresh_news_sources: async () => ({
      status: "started",
      error: null,
      started_at: NOW,
    }),

    set_news_source_enabled: async (params) => ({
      status: "success",
      source_id: params.source_id,
      enabled: params.enabled,
    }),

    set_news_source_priority: async (params) => ({
      status: "success",
      source_id: params.source_id,
      priority: params.priority,
    }),

    add_custom_news_source: async (params) => ({
      status: "success",
      source: {
        source_id: "user_mock_feed",
        name: params.name || "Mock custom feed",
        source_type: "user_provided_rss",
        reliability_layer: "user_provided",
        feed_url: params.feed_url,
        homepage_url: null,
        enabled: params.enabled ?? true,
        priority: params.priority ?? 100,
        user_defined: true,
      },
      validation: {
        title: params.name || "Mock custom feed",
        entry_count: 1,
        http_status: 200,
        final_url: params.feed_url,
      },
    }),

    update_news_article_state: async (params) => ({
      status: "success",
      state: {
        article_id: params.article_id,
        read: params.read ?? false,
        saved: params.saved ?? false,
        hidden: params.hidden ?? false,
        read_later: params.read_later ?? false,
        notes: params.notes ?? null,
      },
    }),
  };
}
