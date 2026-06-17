import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { StateBanner } from "@/components/feedback/StateBanner";
import {
  addCustomNewsSource,
  cleanupNewsExtractedContent,
  fetchNewsArticles,
  fetchNewsCompanyScope,
  fetchNewsCollectionRuns,
  fetchNewsGoogleCompanyFeedSettings,
  fetchNewsOverview,
  fetchNewsRefreshStatus,
  fetchNewsRetentionStatus,
  fetchNewsSources,
  refreshNewsSources,
  saveNewsGoogleCompanyFeedSettings,
  saveNewsRetentionPolicy,
  setNewsCompanyScopeOverride,
  setNewsCompanyScopeUniverse,
  setNewsSourceEnabled,
  setNewsSourcePriority,
  updateNewsArticleState,
} from "@/lib/api/news";
import type {
  NewsArticle,
  NewsCompanyScopeResponse,
  NewsOverviewSection,
  NewsRefreshStatus,
  NewsRetentionStatus,
  NewsGoogleCompanyFeedSettings,
  SaveNewsGoogleCompanyFeedSettingsParams,
  SaveNewsGoogleCompanyFeedSettingsResult,
  SaveNewsRetentionPolicyParams,
  SaveNewsRetentionPolicyResult,
  CleanupNewsExtractedContentResult,
  SetNewsCompanyScopeOverrideParams,
  SetNewsCompanyScopeOverrideResult,
  SetNewsCompanyScopeUniverseParams,
  SetNewsCompanyScopeUniverseResult,
  NewsSource,
} from "@/lib/bridge/types";

type NewsView = "top" | "latest";

const NEWS_PAGE_SIZE = 50;

export function NewsPage() {
  const location = useLocation();
  const view: NewsView = location.pathname.endsWith("/latest") ? "latest" : "top";
  const queryClient = useQueryClient();
  const [sourceFilter, setSourceFilter] = useState("");
  const [searchText, setSearchText] = useState("");
  const [showSavedOnly, setShowSavedOnly] = useState(false);
  const [showReadLaterOnly, setShowReadLaterOnly] = useState(false);
  const [includeHidden, setIncludeHidden] = useState(false);
  const [articleOffset, setArticleOffset] = useState(0);

  const articlesQuery = useQuery({
    queryKey: ["news", "articles", view, sourceFilter, includeHidden, articleOffset],
    queryFn: () =>
      fetchNewsArticles({
        limit: NEWS_PAGE_SIZE,
        offset: articleOffset,
        source_id: sourceFilter || null,
        include_hidden: includeHidden,
        order: view === "top" ? "top" : "latest",
      }),
    refetchInterval: view === "latest" ? 60_000 : false,
  });
  const overviewQuery = useQuery({
    queryKey: ["news", "overview"],
    queryFn: () => fetchNewsOverview({ limit_per_section: 5 }),
    enabled: view === "top",
    refetchInterval: false,
  });
  const sourcesQuery = useQuery({
    queryKey: ["news", "sources"],
    queryFn: fetchNewsSources,
    refetchInterval: 60_000,
  });
  const companyScopeQuery = useQuery({
    queryKey: ["news", "company-scope"],
    queryFn: fetchNewsCompanyScope,
    refetchInterval: 60_000,
  });
  const refreshStatusQuery = useQuery({
    queryKey: ["news", "refresh-status"],
    queryFn: fetchNewsRefreshStatus,
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 2_000 : 15_000,
  });
  const refreshMutation = useMutation({
    mutationFn: refreshNewsSources,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["news"] });
    },
  });
  const companyScopeUniverseMutation = useMutation({
    mutationFn: setNewsCompanyScopeUniverse,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["news"] });
    },
  });
  const articleStateMutation = useMutation({
    mutationFn: updateNewsArticleState,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["news", "articles"] });
    },
  });

  const articles = articlesQuery.data?.items ?? [];
  const overviewSections = overviewQuery.data?.sections ?? [];
  const sources = sourcesQuery.data?.items ?? [];
  const browserReason =
    articlesQuery.data?.mode === "browser" ? articlesQuery.data.reason : null;
  const loadError =
    articlesQuery.error ?? sourcesQuery.error ?? refreshStatusQuery.error;

  const sourceStats = useMemo(() => summarizeSources(sources), [sources]);
  const refreshStatus = refreshStatusQuery.data ?? null;
  const filteredArticles = useMemo(
    () =>
      filterArticles(articles, {
        searchText,
        showSavedOnly,
        showReadLaterOnly,
      }),
    [articles, searchText, showSavedOnly, showReadLaterOnly],
  );
  const frontPage = useMemo(
    () => buildEditorialFrontPage(overviewSections, articles),
    [overviewSections, articles],
  );
  useEffect(() => {
    setArticleOffset(0);
  }, [view, sourceFilter, includeHidden]);

  const loadedCount = articlesQuery.data?.count ?? articles.length;
  const totalCount = articlesQuery.data?.total ?? loadedCount;
  const pageNumber = Math.floor(articleOffset / NEWS_PAGE_SIZE) + 1;
  const pageCount = Math.max(1, Math.ceil(totalCount / NEWS_PAGE_SIZE));
  const canPreviousPage = articleOffset > 0;
  const canNextPage = articleOffset + loadedCount < totalCount;

  return (
    <section className="space-y-3 px-6 py-4">
      {browserReason ? <StateBanner variant="browser-only" message={browserReason} /> : null}

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-wider text-zinc-500">
            Local News
          </p>
          <h1 className="text-xl font-semibold text-zinc-100">News</h1>
          <p className="mt-0.5 max-w-3xl text-sm text-zinc-400">
            Financial news collected into the local News database with explicit source status.
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <NewsUniverseQuickSelect
            scope={companyScopeQuery.data ?? null}
            loading={companyScopeQuery.isLoading}
            saving={companyScopeUniverseMutation.isPending}
            result={companyScopeUniverseMutation.data ?? null}
            onSelect={(params) => companyScopeUniverseMutation.mutate(params)}
          />
          <Button
            type="button"
            variant="primary"
            loading={refreshMutation.isPending || refreshStatus?.status === "running"}
            onClick={() => refreshMutation.mutate()}
            disabled={articlesQuery.data?.mode === "browser"}
          >
            Refresh
          </Button>
        </div>
      </header>

      <NewsStatusStrip
        totalArticles={articlesQuery.data?.total ?? 0}
        sourceStats={sourceStats}
        refreshStatus={refreshStatus}
      />

      {loadError ? (
        <StateBanner
          variant="error"
          title="Could not load News"
          message={loadError instanceof Error ? loadError.message : String(loadError)}
          onRetry={() => {
            void queryClient.invalidateQueries({ queryKey: ["news"] });
          }}
        />
      ) : null}

      {refreshMutation.data?.status === "error" || refreshMutation.data?.status === "blocked" ? (
        <StateBanner
          variant="warning"
          title="Refresh was not started"
          message={refreshMutation.data.error ?? "The News refresh request could not be started."}
          size="dense"
        />
      ) : null}

      {view === "top" ? (
          <EditorialFrontPage
            loading={overviewQuery.isLoading || articlesQuery.isLoading}
            error={overviewQuery.error ?? overviewQuery.data?.error}
            frontPage={frontPage}
          />
      ) : null}

      <div className={`grid gap-4 ${view === "latest" ? "xl:grid-cols-[minmax(0,1fr)_360px]" : ""}`}>
        <main className="min-w-0 rounded-lg border border-zinc-800 bg-zinc-950/40">
          <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
            <div>
              <h2 className="text-sm font-semibold text-zinc-100">
                {view === "latest" ? "Latest" : "More News"}
              </h2>
              <p className="mt-0.5 text-xs text-zinc-500">
                {view === "latest"
                  ? "Chronological local feed"
                  : "Dense ranked list after the front page"}
              </p>
            </div>
            <span className="font-mono text-xs text-zinc-500">
              {articlesQuery.isFetching
                ? "loading"
                : `${filteredArticles.length} shown · page ${pageNumber}/${pageCount}`}
            </span>
          </div>

          <div className="p-4">
            <ArticleFilters
              sources={sources}
              sourceFilter={sourceFilter}
              searchText={searchText}
              showSavedOnly={showSavedOnly}
              showReadLaterOnly={showReadLaterOnly}
              includeHidden={includeHidden}
              onSourceFilterChange={setSourceFilter}
              onSearchTextChange={setSearchText}
              onShowSavedOnlyChange={setShowSavedOnly}
              onShowReadLaterOnlyChange={setShowReadLaterOnly}
              onIncludeHiddenChange={setIncludeHidden}
            />
            {articlesQuery.isLoading ? (
              <StateBanner variant="loading" title="Loading News" />
            ) : articles.length === 0 ? (
              <StateBanner
                variant="empty"
                title="No local articles yet"
                message="Run Refresh to collect enabled sources into the local News database."
              />
            ) : filteredArticles.length === 0 ? (
              <StateBanner
                variant="empty"
                title="No articles match these filters"
                message="Adjust the source, saved/read-later filters, hidden toggle, or search text."
              />
            ) : (
              <>
                <ArticleList
                  articles={filteredArticles}
                  disabled={articleStateMutation.isPending}
                  onUpdate={(params) => articleStateMutation.mutate(params)}
                />
                <ArticlePager
                  canPreviousPage={canPreviousPage}
                  canNextPage={canNextPage}
                  loading={articlesQuery.isFetching}
                  pageNumber={pageNumber}
                  pageCount={pageCount}
                  offset={articleOffset}
                  pageSize={NEWS_PAGE_SIZE}
                  pageLoadedCount={loadedCount}
                  totalCount={totalCount}
                  onPrevious={() =>
                    setArticleOffset((current) => Math.max(0, current - NEWS_PAGE_SIZE))
                  }
                  onNext={() => setArticleOffset((current) => current + NEWS_PAGE_SIZE)}
                />
              </>
            )}
          </div>
        </main>
      </div>
    </section>
  );
}

export function NewsSettingsPanel() {
  const queryClient = useQueryClient();
  const sourcesQuery = useQuery({
    queryKey: ["news", "sources"],
    queryFn: fetchNewsSources,
    refetchInterval: 60_000,
  });
  const companyScopeQuery = useQuery({
    queryKey: ["news", "company-scope"],
    queryFn: fetchNewsCompanyScope,
    refetchInterval: 60_000,
  });
  const googleCompanyFeedsQuery = useQuery({
    queryKey: ["news", "google-company-feeds"],
    queryFn: fetchNewsGoogleCompanyFeedSettings,
    refetchInterval: 60_000,
  });
  const retentionQuery = useQuery({
    queryKey: ["news", "retention"],
    queryFn: fetchNewsRetentionStatus,
    refetchInterval: 60_000,
  });
  const runsQuery = useQuery({
    queryKey: ["news", "runs"],
    queryFn: () => fetchNewsCollectionRuns(5),
    refetchInterval: 60_000,
  });
  const sourceEnabledMutation = useMutation({
    mutationFn: setNewsSourceEnabled,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["news"] });
    },
  });
  const sourcePriorityMutation = useMutation({
    mutationFn: setNewsSourcePriority,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["news"] });
    },
  });
  const addSourceMutation = useMutation({
    mutationFn: addCustomNewsSource,
    onSuccess: (payload) => {
      if (payload.status === "success") {
        void queryClient.invalidateQueries({ queryKey: ["news"] });
      }
    },
  });
  const companyScopeMutation = useMutation({
    mutationFn: setNewsCompanyScopeOverride,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["news", "company-scope"] });
      void queryClient.invalidateQueries({ queryKey: ["news", "overview"] });
    },
  });
  const companyScopeUniverseMutation = useMutation({
    mutationFn: setNewsCompanyScopeUniverse,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["news"] });
    },
  });
  const saveRetentionMutation = useMutation({
    mutationFn: saveNewsRetentionPolicy,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["news", "retention"] });
    },
  });
  const googleCompanyFeedsMutation = useMutation({
    mutationFn: saveNewsGoogleCompanyFeedSettings,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["news"] });
    },
  });
  const cleanupRetentionMutation = useMutation({
    mutationFn: cleanupNewsExtractedContent,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["news"] });
    },
  });

  const sourceMutationPending = sourceEnabledMutation.isPending || sourcePriorityMutation.isPending;
  const pendingSourceId =
    sourceEnabledMutation.isPending
      ? sourceEnabledMutation.variables?.source_id ?? null
      : sourcePriorityMutation.isPending
        ? sourcePriorityMutation.variables?.source_id ?? null
        : null;
  const sources = sourcesQuery.data?.items ?? [];
  const runs = runsQuery.data?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.45fr)]">
        <SourceHealthPanel
          sources={sources}
          loading={sourcesQuery.isLoading}
          disabled={sourceMutationPending}
          pendingSourceId={pendingSourceId}
          onToggleSource={(source, enabled) =>
            sourceEnabledMutation.mutate({ source_id: source.source_id, enabled })
          }
          onPriorityChange={(source, priority) =>
            sourcePriorityMutation.mutate({ source_id: source.source_id, priority })
          }
        />
        <AddSourcePanel
          disabled={addSourceMutation.isPending}
          loading={addSourceMutation.isPending}
          result={addSourceMutation.data ?? null}
          onSubmit={(params) => addSourceMutation.mutate(params)}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <NewsCompanyScopePanel
          scope={companyScopeQuery.data ?? null}
          loading={companyScopeQuery.isLoading}
          disabled={companyScopeMutation.isPending || companyScopeUniverseMutation.isPending}
          result={companyScopeMutation.data ?? null}
          universeResult={companyScopeUniverseMutation.data ?? null}
          onSetOverride={(params) => companyScopeMutation.mutate(params)}
          onSelectUniverse={(params) => companyScopeUniverseMutation.mutate(params)}
        />
        <GoogleCompanyFeedsPanel
          settings={googleCompanyFeedsQuery.data ?? null}
          loading={googleCompanyFeedsQuery.isLoading}
          saving={googleCompanyFeedsMutation.isPending}
          result={googleCompanyFeedsMutation.data ?? null}
          onSave={(params) => googleCompanyFeedsMutation.mutate(params)}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <NewsRetentionPanel
          status={retentionQuery.data ?? null}
          loading={retentionQuery.isLoading}
          saving={saveRetentionMutation.isPending}
          cleaning={cleanupRetentionMutation.isPending}
          saveResult={saveRetentionMutation.data ?? null}
          cleanupResult={cleanupRetentionMutation.data ?? null}
          onSave={(params) => saveRetentionMutation.mutate(params)}
          onCleanup={(dryRun) => cleanupRetentionMutation.mutate({ dry_run: dryRun })}
        />
      </div>

      <RunsPanel runs={runs} loading={runsQuery.isLoading} />
    </div>
  );
}

type EditorialFrontPageModel = {
  lead: NewsArticle | null;
  secondary: NewsArticle[];
  critical: NewsArticle[];
  macro: NewsArticle[];
  companies: NewsArticle[];
  sectors: NewsArticle[];
  keywords: NewsArticle[];
};

function NewsStatusStrip({
  totalArticles,
  sourceStats,
  refreshStatus,
}: {
  totalArticles: number;
  sourceStats: ReturnType<typeof summarizeSources>;
  refreshStatus: NewsRefreshStatus | null;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-y border-zinc-900 py-2 font-mono text-[11px] uppercase text-zinc-500">
      <span>{totalArticles} local articles</span>
      <span>{sourceStats.enabled} sources enabled</span>
      <span>{sourceStats.healthy} healthy</span>
      <span>Refresh {refreshLabel(refreshStatus)} · {refreshDetail(refreshStatus)}</span>
    </div>
  );
}

function NewsUniverseQuickSelect({
  scope,
  loading,
  saving,
  result,
  onSelect,
}: {
  scope: NewsApiScopeResult | null;
  loading: boolean;
  saving: boolean;
  result: SetNewsCompanyScopeUniverseResult | null;
  onSelect: (params: SetNewsCompanyScopeUniverseParams) => void;
}) {
  const universes = scope?.available_coverage_universes ?? [];
  const selectedId = scope?.selected_coverage_universe_id ?? "";
  const selectedName =
    scope?.selected_coverage_universe_name ||
    (scope?.selected_preset ? `Default: ${scope.selected_preset}` : "Default coverage");
  const count = scope?.included_count ?? scope?.coverage_count ?? 0;
  const statusText =
    result?.status === "success"
      ? "saved"
      : result?.status === "error" || result?.status === "not_found"
        ? "error"
        : saving
          ? "saving"
          : `${count} companies`;

  return (
    <div className="flex min-w-[260px] max-w-full items-center gap-2 rounded-md border border-zinc-800 bg-zinc-950/60 px-2 py-1.5">
      <div className="min-w-0 flex-1">
        <p className="font-mono text-[10px] uppercase text-zinc-500">News universe</p>
        {universes.length > 0 ? (
          <select
            value={selectedId}
            disabled={loading || saving}
            title={selectedName}
            onChange={(event) => onSelect({ coverage_universe_id: event.currentTarget.value || null })}
            className="mt-0.5 h-7 w-full min-w-0 rounded border border-zinc-800 bg-black px-2 text-xs text-zinc-100 outline-none focus:border-amber-500 disabled:opacity-50"
          >
            <option value="">Default coverage</option>
            {universes.map((universe) => (
              <option key={universe.id} value={universe.id}>
                {universe.name} ({universe.company_count})
              </option>
            ))}
          </select>
        ) : (
          <p className="mt-1 truncate text-xs text-zinc-400" title={loading ? "Loading universes" : selectedName}>
            {loading ? "Loading universes" : "No Coverage universes"}
          </p>
        )}
      </div>
      <span
        className={`whitespace-nowrap rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase ${
          statusText === "error"
            ? "border-red-500/40 text-red-300"
            : statusText === "saved"
              ? "border-emerald-500/40 text-emerald-300"
              : "border-zinc-800 text-zinc-500"
        }`}
      >
        {statusText}
      </span>
    </div>
  );
}

function EditorialFrontPage({
  loading,
  error,
  frontPage,
}: {
  loading: boolean;
  error: unknown;
  frontPage: EditorialFrontPageModel;
}) {
  if (loading) {
    return <StateBanner variant="loading" title="Building front page" />;
  }
  if (error) {
    return (
      <StateBanner
        variant="warning"
        title="Front page unavailable"
        message={error instanceof Error ? error.message : String(error)}
        size="dense"
      />
    );
  }
  if (!frontPage.lead) {
    return (
      <StateBanner
        variant="empty"
        title="No front page yet"
        message="Run Refresh to collect enabled sources into the local News database."
      />
    );
  }

  return (
    <div className="space-y-3">
      {frontPage.critical.length ? (
        <CriticalNewsStrip articles={frontPage.critical} />
      ) : null}

      <section className="overflow-hidden border-y border-zinc-800 py-4">
        <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.9fr)_minmax(250px,290px)] 2xl:grid-cols-[minmax(0,0.9fr)_minmax(0,0.95fr)_minmax(0,0.85fr)]">
          <LeadStory
            article={frontPage.lead}
          />
          <div className="min-w-0 space-y-3 border-zinc-800 xl:border-x xl:px-4">
            <EditorialColumn
              title="Secondary Lead"
              articles={frontPage.secondary}
            />
          </div>
          <aside className="min-w-0 space-y-4 2xl:grid 2xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] 2xl:gap-x-5 2xl:gap-y-4 2xl:space-y-0">
            <EditorialRail
              title="Macro Watch"
              articles={frontPage.macro}
            />
            <EditorialRail
              title="My Companies"
              articles={frontPage.companies}
            />
            <div className="hidden 2xl:block">
              <EditorialRail
                title="My Sectors"
                articles={frontPage.sectors}
              />
            </div>
            <div className="hidden 2xl:block">
              <EditorialRail
                title="Keyword Alerts"
                articles={frontPage.keywords}
              />
            </div>
          </aside>
        </div>
      </section>
    </div>
  );
}

function LeadStory({
  article,
}: {
  article: NewsArticle;
}) {
  const summary = plainArticleSummary(article.summary);
  return (
    <article className="min-w-0">
      <div className="flex flex-wrap items-center gap-2 font-mono text-[11px] uppercase text-zinc-500">
        <span className="text-amber-300">{article.source_name}</span>
        <time>{formatDate(article.published_at ?? article.discovered_at)}</time>
        <PriorityPill priority={article.priority_level ?? "Normal"} />
        <ContentStatus status={article.content_status} paywall={article.paywall_status} />
      </div>
      <a
        href={article.original_url}
        target="_blank"
        rel="noreferrer"
        className="mt-2 block text-left"
      >
        <h2 className="max-w-4xl text-3xl font-semibold leading-[1.06] text-zinc-50 [overflow-wrap:anywhere] lg:text-4xl 2xl:text-5xl">
          {article.title}
        </h2>
      </a>
      {summary ? (
        <p className="mt-3 line-clamp-4 max-w-3xl text-sm leading-6 text-zinc-300 2xl:text-base 2xl:leading-7">{summary}</p>
      ) : null}
      <div className="mt-3 grid gap-2 md:grid-cols-2">
        {(article.relevance_reasons ?? []).slice(0, 2).map((reason) => (
          <p key={reason} className="border-l border-amber-600/50 pl-3 text-xs leading-5 text-zinc-300 2xl:text-sm">
            {reason}
          </p>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <a
          href={article.original_url}
          target="_blank"
          rel="noreferrer"
          className="rounded border border-zinc-700 px-3 py-1.5 text-sm text-zinc-200 hover:border-amber-500 hover:text-amber-200"
        >
          Open original
        </a>
      </div>
    </article>
  );
}

function CriticalNewsStrip({
  articles,
}: {
  articles: NewsArticle[];
}) {
  return (
    <section className="border-y border-red-900/70 bg-red-950/10 px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono text-[11px] uppercase text-red-300">Critical News</span>
        {articles.slice(0, 3).map((article) => (
          <a
            key={article.article_id}
            href={article.original_url}
            target="_blank"
            rel="noreferrer"
            className="text-left text-sm font-medium text-zinc-100 hover:text-red-200"
          >
            {article.title}
          </a>
        ))}
      </div>
    </section>
  );
}

function EditorialColumn({
  title,
  articles,
}: {
  title: string;
  articles: NewsArticle[];
}) {
  return (
    <section>
      <h3 className="border-b border-zinc-800 pb-2 font-mono text-[11px] uppercase tracking-wider text-zinc-500">
        {title}
      </h3>
      <div className="divide-y divide-zinc-800">
        {articles.length ? (
          articles.map((article) => (
            <EditorialStoryLine
              key={article.article_id}
              article={article}
              size="medium"
            />
          ))
        ) : (
          <EditorialEmpty message="No secondary story available." />
        )}
      </div>
    </section>
  );
}

function EditorialRail({
  title,
  articles,
}: {
  title: string;
  articles: NewsArticle[];
}) {
  return (
    <section>
      <h3 className="border-b border-zinc-800 pb-2 font-mono text-[11px] uppercase tracking-wider text-amber-200">
        {title}
      </h3>
      <div className="divide-y divide-zinc-800">
        {articles.length ? (
          articles.slice(0, 4).map((article) => (
            <EditorialStoryLine
              key={article.article_id}
              article={article}
              size="small"
            />
          ))
        ) : (
          <EditorialEmpty message="No matching local articles." />
        )}
      </div>
    </section>
  );
}

function EditorialStoryLine({
  article,
  size,
}: {
  article: NewsArticle;
  size: "medium" | "small";
}) {
  const summary = plainArticleSummary(article.summary);
  return (
    <article className="min-w-0 py-2.5">
      <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase text-zinc-500">
        <span className="text-amber-200">{article.source_name}</span>
        <time>{formatDate(article.published_at ?? article.discovered_at)}</time>
        {article.priority_level && article.priority_level !== "Normal" ? (
          <PriorityPill priority={article.priority_level} />
        ) : null}
      </div>
      <a href={article.original_url} target="_blank" rel="noreferrer" className="mt-1 block text-left">
        <h4 className={`${size === "medium" ? "text-lg leading-6 2xl:text-xl" : "text-sm leading-5"} font-semibold text-zinc-100 [overflow-wrap:anywhere] hover:text-amber-200`}>
          {article.title}
        </h4>
      </a>
      {size === "medium" && summary ? (
        <p className="mt-1 line-clamp-1 text-sm leading-5 text-zinc-400 2xl:line-clamp-2">{summary}</p>
      ) : null}
    </article>
  );
}

function EditorialEmpty({ message }: { message: string }) {
  return <p className="py-3 text-sm text-zinc-500">{message}</p>;
}

function ArticleFilters({
  sources,
  sourceFilter,
  searchText,
  showSavedOnly,
  showReadLaterOnly,
  includeHidden,
  onSourceFilterChange,
  onSearchTextChange,
  onShowSavedOnlyChange,
  onShowReadLaterOnlyChange,
  onIncludeHiddenChange,
}: {
  sources: NewsSource[];
  sourceFilter: string;
  searchText: string;
  showSavedOnly: boolean;
  showReadLaterOnly: boolean;
  includeHidden: boolean;
  onSourceFilterChange: (value: string) => void;
  onSearchTextChange: (value: string) => void;
  onShowSavedOnlyChange: (value: boolean) => void;
  onShowReadLaterOnlyChange: (value: boolean) => void;
  onIncludeHiddenChange: (value: boolean) => void;
}) {
  return (
    <div className="mb-4 rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="grid gap-3 md:grid-cols-[minmax(180px,240px)_1fr]">
        <label className="space-y-1">
          <span className="font-mono text-[11px] uppercase text-zinc-500">Source</span>
          <select
            value={sourceFilter}
            onChange={(event) => onSourceFilterChange(event.currentTarget.value)}
            className="h-8 w-full rounded-md border border-zinc-700 bg-zinc-950 px-2 text-sm text-zinc-100 outline-none focus:border-amber-500"
          >
            <option value="">All sources</option>
            {sources.map((source) => (
              <option key={source.source_id} value={source.source_id}>
                {source.name}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1">
          <span className="font-mono text-[11px] uppercase text-zinc-500">Search</span>
          <Input
            value={searchText}
            placeholder="Title, source, snippet, URL"
            onChange={(event) => onSearchTextChange(event.currentTarget.value)}
          />
        </label>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <ToggleChip
          active={showSavedOnly}
          label="Saved"
          onChange={onShowSavedOnlyChange}
        />
        <ToggleChip
          active={showReadLaterOnly}
          label="Read later"
          onChange={onShowReadLaterOnlyChange}
        />
        <ToggleChip
          active={includeHidden}
          label="Hidden"
          onChange={onIncludeHiddenChange}
        />
      </div>
    </div>
  );
}

function ArticlePager({
  canPreviousPage,
  canNextPage,
  loading,
  pageNumber,
  pageCount,
  offset,
  pageSize,
  pageLoadedCount,
  totalCount,
  onPrevious,
  onNext,
}: {
  canPreviousPage: boolean;
  canNextPage: boolean;
  loading: boolean;
  pageNumber: number;
  pageCount: number;
  offset: number;
  pageSize: number;
  pageLoadedCount: number;
  totalCount: number;
  onPrevious: () => void;
  onNext: () => void;
}) {
  const firstItem = totalCount === 0 ? 0 : offset + 1;
  const lastItem = Math.min(offset + pageLoadedCount, totalCount);

  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-zinc-800 pt-4">
      <p className="font-mono text-[11px] uppercase text-zinc-500">
        {firstItem}-{lastItem} of {totalCount} · page {pageNumber}/{pageCount} · {pageSize} per page
      </p>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={!canPreviousPage || loading}
          onClick={onPrevious}
        >
          Previous
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          loading={loading}
          disabled={!canNextPage || loading}
          onClick={onNext}
        >
          Next
        </Button>
      </div>
    </div>
  );
}

function ToggleChip({
  active,
  label,
  onChange,
}: {
  active: boolean;
  label: string;
  onChange: (value: boolean) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!active)}
      className="rounded border px-2 py-1 font-mono text-[11px] uppercase"
      style={{
        borderColor: active ? "var(--color-action-primary)" : "var(--color-border-default)",
        color: active ? "var(--color-action-primary)" : "var(--color-text-secondary)",
        background: active ? "rgba(245, 165, 36, 0.08)" : "transparent",
      }}
    >
      {label}
    </button>
  );
}

function ArticleList({
  articles,
  disabled,
  onUpdate,
}: {
  articles: NewsArticle[];
  disabled?: boolean;
  onUpdate: (params: {
    article_id: string;
    read?: boolean;
    saved?: boolean;
    hidden?: boolean;
    read_later?: boolean;
    notes?: string | null;
  }) => void;
}) {
  return (
    <div className="space-y-2">
      {articles.map((article) => (
        <ArticleRow
          key={article.article_id}
          article={article}
          disabled={disabled}
          onUpdate={onUpdate}
        />
      ))}
    </div>
  );
}

function ArticleRow({
  article,
  disabled,
  onUpdate,
}: {
  article: NewsArticle;
  disabled?: boolean;
  onUpdate: (params: {
    article_id: string;
    read?: boolean;
    saved?: boolean;
    hidden?: boolean;
    read_later?: boolean;
    notes?: string | null;
  }) => void;
}) {
  const [note, setNote] = useState(article.notes ?? "");
  const isRead = Boolean(article.read);
  const isSaved = Boolean(article.saved);
  const isReadLater = Boolean(article.read_later);

  useEffect(() => {
    setNote(article.notes ?? "");
  }, [article.notes]);

  return (
    <article
      className={`rounded-md border border-transparent px-3 py-3 first:mt-0 last:mb-0 ${isRead ? "opacity-75" : ""}`}
    >
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-mono text-amber-200">{article.source_name}</span>
        <span className="text-zinc-600">·</span>
        <time className="font-mono text-zinc-500">{formatDate(article.published_at ?? article.discovered_at)}</time>
        <ContentStatus status={article.content_status} paywall={article.paywall_status} />
        <PriorityPill priority={article.priority_level ?? "Normal"} />
        {isSaved ? <StatusPill status="saved" /> : null}
        {isReadLater ? <StatusPill status="read_later" /> : null}
      </div>
      <a
        href={article.original_url}
        target="_blank"
        rel="noreferrer"
        className="mt-1 block text-sm font-medium text-zinc-100 hover:text-amber-200"
      >
        {article.title}
      </a>
      {article.summary ? (
        <p className="mt-1 line-clamp-2 text-sm text-zinc-400">{article.summary}</p>
      ) : null}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] uppercase text-zinc-500">
        <ArticleTextAction
          disabled={disabled}
          onClick={() => onUpdate({ article_id: article.article_id, read: !isRead })}
        >
          {isRead ? "Unread" : "Read"}
        </ArticleTextAction>
        <ArticleTextAction
          disabled={disabled}
          onClick={() => onUpdate({ article_id: article.article_id, saved: !isSaved })}
          active={isSaved}
        >
          {isSaved ? "Saved" : "Save"}
        </ArticleTextAction>
        <ArticleTextAction
          disabled={disabled}
          onClick={() => onUpdate({ article_id: article.article_id, read_later: !isReadLater })}
          active={isReadLater}
        >
          Later
        </ArticleTextAction>
        <ArticleTextAction
          disabled={disabled}
          onClick={() => onUpdate({ article_id: article.article_id, hidden: true })}
        >
          Hide
        </ArticleTextAction>
      </div>
      {article.notes ? (
        <form
          className="mt-2 grid grid-cols-[1fr_auto] gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            onUpdate({ article_id: article.article_id, notes: note.trim() });
          }}
        >
          <Input
            value={note}
            disabled={disabled}
            placeholder="Short note"
            onChange={(event) => setNote(event.currentTarget.value)}
          />
          <Button type="submit" size="xs" variant="secondary" disabled={disabled}>
            Note
          </Button>
        </form>
      ) : null}
    </article>
  );
}

function ArticleTextAction({
  active,
  disabled,
  children,
  onClick,
}: {
  active?: boolean;
  disabled?: boolean;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`transition-colors hover:text-amber-200 disabled:opacity-50 ${
        active ? "text-amber-200" : "text-zinc-500"
      }`}
    >
      {children}
    </button>
  );
}

function SourceHealthPanel({
  sources,
  loading,
  disabled,
  pendingSourceId,
  onToggleSource,
  onPriorityChange,
}: {
  sources: NewsSource[];
  loading: boolean;
  disabled?: boolean;
  pendingSourceId: string | null;
  onToggleSource: (source: NewsSource, enabled: boolean) => void;
  onPriorityChange: (source: NewsSource, priority: number) => void;
}) {
  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-950/40">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">Sources</h2>
          <p className="mt-0.5 text-xs text-zinc-500">Enabled feeds, health, and collection priority.</p>
        </div>
        <span className="font-mono text-[11px] uppercase text-zinc-500">
          {sources.filter((source) => Boolean(source.enabled)).length}/{sources.length} enabled
        </span>
      </div>
      <div>
        {loading ? (
          <div className="p-4">
            <StateBanner variant="loading" title="Loading sources" size="dense" />
          </div>
        ) : sources.length === 0 ? (
          <div className="p-4">
            <StateBanner variant="empty" title="No sources" size="dense" />
          </div>
        ) : (
          <div className="divide-y divide-zinc-800">
            {sources.map((source) => (
              <SourceRow
                key={source.source_id}
                source={source}
                disabled={disabled || pendingSourceId === source.source_id}
                onToggleSource={onToggleSource}
                onPriorityChange={onPriorityChange}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function SourceRow({
  source,
  disabled,
  onToggleSource,
  onPriorityChange,
}: {
  source: NewsSource;
  disabled?: boolean;
  onToggleSource: (source: NewsSource, enabled: boolean) => void;
  onPriorityChange: (source: NewsSource, priority: number) => void;
}) {
  const [priorityValue, setPriorityValue] = useState(String(source.priority));
  const enabled = Boolean(source.enabled);

  useEffect(() => {
    setPriorityValue(String(source.priority));
  }, [source.priority]);

  return (
    <div className={`grid gap-3 px-4 py-3 md:grid-cols-[minmax(0,1fr)_110px_92px] md:items-center ${enabled ? "" : "opacity-60"}`}>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <p className="min-w-0 truncate text-sm font-medium text-zinc-100">{source.name}</p>
          <StatusPill status={source.last_status ?? (source.enabled ? "pending" : "disabled")} />
        </div>
        <p className="mt-1 font-mono text-[11px] uppercase text-zinc-500">
          {source.reliability_layer}
          {source.allow_content_storage ? " · local content eligible" : ""}
          {source.last_success_at ? ` · last success ${formatDate(source.last_success_at)}` : ""}
        </p>
        {source.last_error ? (
          <p className="mt-1 text-xs text-red-300">{source.last_error}</p>
        ) : null}
      </div>
      <label className="space-y-1">
        <span className="font-mono text-[10px] uppercase text-zinc-500">Priority</span>
        <div className="max-w-28">
          <Input
            type="number"
            min={1}
            max={1000}
            value={priorityValue}
            disabled={disabled}
            mono
            onChange={(event) => setPriorityValue(event.currentTarget.value)}
            onBlur={() => {
              const parsed = Number(priorityValue);
              if (Number.isFinite(parsed) && parsed !== source.priority) {
                onPriorityChange(source, parsed);
              } else {
                setPriorityValue(String(source.priority));
              }
            }}
          />
        </div>
      </label>
      <div className="flex justify-start md:justify-end">
        <Button
          type="button"
          size="xs"
          variant={enabled ? "secondary" : "primary"}
          disabled={disabled}
          onClick={() => onToggleSource(source, !enabled)}
        >
          {enabled ? "Disable" : "Enable"}
        </Button>
      </div>
    </div>
  );
}

function GoogleCompanyFeedsPanel({
  settings,
  loading,
  saving,
  result,
  onSave,
}: {
  settings: NewsApiGoogleCompanyFeedsResult | null;
  loading: boolean;
  saving: boolean;
  result: SaveNewsGoogleCompanyFeedSettingsResult | null;
  onSave: (params: SaveNewsGoogleCompanyFeedSettingsParams) => void;
}) {
  const [enabled, setEnabled] = useState(false);
  const [maxCompanies, setMaxCompanies] = useState("50");
  const [priority, setPriority] = useState("140");
  const [locale, setLocale] = useState("pt-BR");
  const [country, setCountry] = useState("BR");

  useEffect(() => {
    if (!settings) return;
    setEnabled(Boolean(settings.enabled));
    setMaxCompanies(String(settings.max_companies ?? 50));
    setPriority(String(settings.priority ?? 140));
    setLocale(settings.locale || "pt-BR");
    setCountry(settings.country || "BR");
  }, [settings]);

  const generatedCount = settings?.generated_count ?? result?.settings?.generated_count ?? 0;
  const eligibleCompanyCount = settings?.eligible_company_count ?? result?.settings?.eligible_company_count ?? 0;
  const scopeIsEmpty = eligibleCompanyCount === 0;

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-950/40">
      <div className="border-b border-zinc-800 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">Google News Company Feeds</h2>
            <p className="mt-0.5 text-xs text-zinc-500">
              Optional aggregator feeds for companies in the News scope.
            </p>
          </div>
          <StatusPill status={enabled ? "enabled" : "disabled"} />
        </div>
      </div>
      <div className="space-y-3 p-4">
        {loading ? (
          <StateBanner variant="loading" title="Loading Google News settings" size="dense" />
        ) : settings?.error ? (
          <StateBanner variant="warning" title="Google News settings unavailable" message={settings.error} size="dense" />
        ) : null}

        <p className="text-xs leading-5 text-zinc-500">
          Uses Google News RSS search URLs per company. These are treated as aggregator sources, not official
          company or regulatory sources, and remain lower priority than direct feeds.
        </p>
        <div className="grid grid-cols-2 gap-2">
          <MetricMini label="Eligible companies" value={eligibleCompanyCount} />
          <MetricMini label="Generated feeds" value={generatedCount} />
        </div>
        {scopeIsEmpty ? (
          <StateBanner
            variant="warning"
            title="No company scope available"
            message="Google News company feeds appear in Sources only after the News company scope has companies from coverage or News-specific inclusions."
            size="dense"
          />
        ) : null}

        <label className="flex items-start gap-3 rounded-md border border-zinc-800 bg-black/20 p-3">
          <input
            type="checkbox"
            className="mt-1 h-4 w-4 accent-amber-500"
            checked={enabled}
            disabled={saving}
            onChange={(event) => setEnabled(event.currentTarget.checked)}
          />
          <span>
            <span className="block text-sm font-medium text-zinc-100">Enable generated company feeds</span>
            <span className="block text-xs leading-5 text-zinc-500">
              Generates up to {maxCompanies || "0"} local source entries from {eligibleCompanyCount} eligible companies.
            </span>
          </span>
        </label>

        <div className="grid gap-3 sm:grid-cols-4">
          <label className="space-y-1 sm:col-span-2">
            <span className="font-mono text-[10px] uppercase text-zinc-500">Max companies</span>
            <Input
              type="number"
              min={1}
              max={250}
              value={maxCompanies}
              disabled={saving}
              mono
              onChange={(event) => setMaxCompanies(event.currentTarget.value)}
            />
          </label>
          <label className="space-y-1">
            <span className="font-mono text-[10px] uppercase text-zinc-500">Priority</span>
            <Input
              type="number"
              min={1}
              max={1000}
              value={priority}
              disabled={saving}
              mono
              onChange={(event) => setPriority(event.currentTarget.value)}
            />
          </label>
          <label className="space-y-1">
            <span className="font-mono text-[10px] uppercase text-zinc-500">Country</span>
            <Input
              value={country}
              disabled={saving}
              mono
              onChange={(event) => setCountry(event.currentTarget.value.toUpperCase())}
            />
          </label>
        </div>

        <label className="space-y-1">
          <span className="font-mono text-[10px] uppercase text-zinc-500">Locale</span>
          <Input
            value={locale}
            disabled={saving}
            mono
            onChange={(event) => setLocale(event.currentTarget.value)}
          />
        </label>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-900 pt-3">
          <p className="font-mono text-[11px] uppercase text-zinc-500">
            {enabled && scopeIsEmpty
              ? "No generated sources until companies are available"
              : `${generatedCount} generated source${generatedCount === 1 ? "" : "s"}`}
          </p>
          <Button
            type="button"
            size="xs"
            disabled={saving}
            onClick={() =>
              onSave({
                enabled,
                max_companies: Number(maxCompanies),
                priority: Number(priority),
                locale,
                country,
              })
            }
          >
            {saving ? "Saving" : "Save"}
          </Button>
        </div>
        {result?.error ? (
          <StateBanner variant="warning" title="Google News settings were not saved" message={result.error} size="dense" />
        ) : result?.status === "success" ? (
          <StateBanner variant="success" title="Google News settings saved" size="dense" />
        ) : null}
      </div>
    </section>
  );
}

function NewsCompanyScopePanel({
  scope,
  loading,
  disabled,
  result,
  universeResult,
  onSetOverride,
  onSelectUniverse,
}: {
  scope: NewsApiScopeResult | null;
  loading: boolean;
  disabled?: boolean;
  result: SetNewsCompanyScopeOverrideResult | null;
  universeResult: SetNewsCompanyScopeUniverseResult | null;
  onSetOverride: (params: SetNewsCompanyScopeOverrideParams) => void;
  onSelectUniverse: (params: SetNewsCompanyScopeUniverseParams) => void;
}) {
  const [companyId, setCompanyId] = useState("");
  const [action, setAction] = useState<"include" | "exclude">("include");
  const [reason, setReason] = useState("News-specific company scope override");
  const overrides = scope?.overrides ?? [];
  const universes = scope?.available_coverage_universes ?? [];

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-950/40">
      <div className="border-b border-zinc-800 px-4 py-3">
        <h2 className="text-sm font-semibold text-zinc-100">My Companies Scope</h2>
      </div>
      <div className="space-y-3 p-4">
        {loading ? (
          <StateBanner variant="loading" title="Loading company scope" size="dense" />
        ) : scope?.error ? (
          <StateBanner variant="warning" title="Scope unavailable" message={scope.error} size="dense" />
        ) : (
          <div className="grid grid-cols-3 gap-2">
            <MetricMini label="Coverage" value={scope?.coverage_count ?? 0} />
            <MetricMini label="Included" value={scope?.included_count ?? 0} />
            <MetricMini label="Excluded" value={scope?.excluded_count ?? 0} />
          </div>
        )}
        <p className="text-xs leading-5 text-zinc-500">
          Uses the Coverage universe selected for News, plus News-specific inclusions and exclusions. This does not
          change the active Coverage universe.
        </p>
        <label className="space-y-1">
          <span className="font-mono text-[10px] uppercase text-zinc-500">Coverage universe for News</span>
          <select
            className="h-9 w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none transition-colors focus:border-amber-500 disabled:opacity-50"
            value={scope?.selected_coverage_universe_id ?? ""}
            disabled={disabled || loading}
            onChange={(event) =>
              onSelectUniverse({ coverage_universe_id: event.currentTarget.value || null })
            }
          >
            <option value="">Default coverage universe</option>
            {universes.map((universe) => (
              <option key={universe.id} value={universe.id}>
                {universe.name} ({universe.company_count})
              </option>
            ))}
          </select>
        </label>
        <p className="font-mono text-[11px] uppercase text-zinc-500">
          {scope?.selected_coverage_universe_name
            ? `News universe: ${scope.selected_coverage_universe_name}`
            : scope?.selected_preset
              ? `Default preset: ${scope.selected_preset}`
              : "Default coverage fallback"}
        </p>
        {universes.length === 0 && !loading ? (
          <StateBanner
            variant="warning"
            title="No Coverage universes found"
            message="Create or populate a Coverage universe first, then select it here for News."
            size="dense"
          />
        ) : null}
        {universeResult?.status === "error" || universeResult?.status === "not_found" ? (
          <StateBanner
            variant="warning"
            title="News universe was not updated"
            message={universeResult.error ?? "Coverage universe selection failed."}
            size="dense"
          />
        ) : universeResult?.status === "success" ? (
          <StateBanner variant="success" title="News universe saved" size="dense" />
        ) : null}
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            const parsed = Number(companyId);
            if (!Number.isFinite(parsed) || parsed <= 0) return;
            onSetOverride({
              cd_cvm: parsed,
              action,
              reason: reason.trim() || null,
            });
          }}
        >
          <div className="grid grid-cols-[1fr_112px] gap-2">
            <Input
              type="number"
              value={companyId}
              disabled={disabled}
              placeholder="CVM code"
              onChange={(event) => setCompanyId(event.currentTarget.value)}
            />
            <select
              value={action}
              disabled={disabled}
              onChange={(event) => setAction(event.currentTarget.value as "include" | "exclude")}
              className="h-8 rounded-md border border-zinc-700 bg-zinc-950 px-2 text-sm text-zinc-100 outline-none focus:border-amber-500"
            >
              <option value="include">Include</option>
              <option value="exclude">Exclude</option>
            </select>
          </div>
          <Input
            value={reason}
            disabled={disabled}
            placeholder="Reason"
            onChange={(event) => setReason(event.currentTarget.value)}
          />
          <Button
            type="submit"
            size="xs"
            variant="secondary"
            disabled={disabled || !companyId.trim()}
          >
            Save override
          </Button>
          {result?.status === "error" ? (
            <p className="text-xs text-red-300">{result.error ?? "Scope update failed."}</p>
          ) : result?.status === "success" ? (
            <p className="text-xs text-emerald-300">Scope override saved.</p>
          ) : null}
        </form>
        {overrides.length > 0 ? (
          <div className="space-y-2">
            {overrides.slice(0, 8).map((override) => (
              <div key={override.cd_cvm} className="flex items-start justify-between gap-2 rounded border border-zinc-800 bg-zinc-900/40 px-2 py-2 text-xs">
                <div>
                  <p className="font-mono text-zinc-200">
                    CVM {override.cd_cvm} · {override.action}
                  </p>
                  {override.reason ? <p className="mt-0.5 text-zinc-500">{override.reason}</p> : null}
                </div>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => onSetOverride({ cd_cvm: override.cd_cvm, action: null })}
                  className="font-mono text-[10px] uppercase text-zinc-500 hover:text-red-300 disabled:opacity-50"
                >
                  Clear
                </button>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}

type NewsApiScopeResult = NewsCompanyScopeResponse & { mode?: string; reason?: string };
type NewsApiGoogleCompanyFeedsResult = NewsGoogleCompanyFeedSettings & { mode?: string; reason?: string };

function NewsRetentionPanel({
  status,
  loading,
  disabled,
  saving,
  cleaning,
  saveResult,
  cleanupResult,
  onSave,
  onCleanup,
}: {
  status: NewsApiRetentionResult | null;
  loading: boolean;
  disabled?: boolean;
  saving: boolean;
  cleaning: boolean;
  saveResult: SaveNewsRetentionPolicyResult | null;
  cleanupResult: CleanupNewsExtractedContentResult | null;
  onSave: (params: SaveNewsRetentionPolicyParams) => void;
  onCleanup: (dryRun: boolean) => void;
}) {
  const policy = status?.policy;
  const [textDays, setTextDays] = useState(String(policy?.extracted_text_retention_days ?? 90));
  const [storageLimit, setStorageLimit] = useState(String(policy?.total_storage_limit_mb ?? 512));
  const [preserveSaved, setPreserveSaved] = useState(Boolean(policy?.preserve_saved ?? true));
  const [preserveOfficial, setPreserveOfficial] = useState(Boolean(policy?.preserve_official_documents ?? true));

  useEffect(() => {
    if (!policy) return;
    setTextDays(String(policy.extracted_text_retention_days));
    setStorageLimit(String(policy.total_storage_limit_mb));
    setPreserveSaved(Boolean(policy.preserve_saved));
    setPreserveOfficial(Boolean(policy.preserve_official_documents));
  }, [policy]);

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-950/40">
      <div className="border-b border-zinc-800 px-4 py-3">
        <h2 className="text-sm font-semibold text-zinc-100">Retention</h2>
      </div>
      <div className="space-y-3 p-4">
        {loading ? (
          <StateBanner variant="loading" title="Loading retention" size="dense" />
        ) : status?.error ? (
          <StateBanner variant="warning" title="Retention unavailable" message={status.error} size="dense" />
        ) : (
          <div className="grid grid-cols-3 gap-2">
            <MetricMini label="Copies" value={status?.content_count ?? 0} />
            <MetricMini label="Saved" value={status?.saved_content_count ?? 0} />
            <MetricMini label="Size" value={formatBytes(status?.storage_bytes ?? 0)} />
          </div>
        )}
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            onSave({
              extracted_text_retention_days: Number(textDays),
              total_storage_limit_mb: Number(storageLimit),
              preserve_saved: preserveSaved,
              preserve_official_documents: preserveOfficial,
            });
          }}
        >
          <div className="grid grid-cols-2 gap-2">
            <label className="space-y-1">
              <span className="font-mono text-[11px] uppercase text-zinc-500">Text days</span>
              <Input
                type="number"
                min={1}
                max={3650}
                value={textDays}
                disabled={disabled || saving}
                onChange={(event) => setTextDays(event.currentTarget.value)}
              />
            </label>
            <label className="space-y-1">
              <span className="font-mono text-[11px] uppercase text-zinc-500">Limit MB</span>
              <Input
                type="number"
                min={16}
                max={10240}
                value={storageLimit}
                disabled={disabled || saving}
                onChange={(event) => setStorageLimit(event.currentTarget.value)}
              />
            </label>
          </div>
          <label className="flex items-center gap-2 text-xs text-zinc-400">
            <input
              type="checkbox"
              checked={preserveSaved}
              disabled={disabled || saving}
              onChange={(event) => setPreserveSaved(event.currentTarget.checked)}
            />
            Preserve saved articles
          </label>
          <label className="flex items-center gap-2 text-xs text-zinc-400">
            <input
              type="checkbox"
              checked={preserveOfficial}
              disabled={disabled || saving}
              onChange={(event) => setPreserveOfficial(event.currentTarget.checked)}
            />
            Preserve official documents
          </label>
          <Button type="submit" size="xs" variant="secondary" loading={saving} disabled={disabled || saving}>
            Save policy
          </Button>
          {saveResult?.status === "error" ? (
            <p className="text-xs text-red-300">{saveResult.error ?? "Could not save policy."}</p>
          ) : saveResult?.status === "success" ? (
            <p className="text-xs text-emerald-300">Policy saved.</p>
          ) : null}
        </form>
        <div className="flex flex-wrap gap-2 border-t border-zinc-800 pt-3">
          <Button
            type="button"
            size="xs"
            variant="secondary"
            disabled={disabled || cleaning}
            onClick={() => onCleanup(true)}
          >
            Preview cleanup
          </Button>
          <Button
            type="button"
            size="xs"
            variant="ghost"
            loading={cleaning}
            disabled={disabled || cleaning}
            onClick={() => onCleanup(false)}
          >
            Clear extracted content
          </Button>
        </div>
        {cleanupResult?.status === "success" ? (
          <p className="text-xs text-zinc-400">
            {cleanupResult.dry_run ? "Preview" : "Cleanup"}: {cleanupResult.deleted_content_count ?? 0} copies,
            {" "}{formatBytes(cleanupResult.freed_bytes ?? 0)}.
          </p>
        ) : cleanupResult?.status === "error" ? (
          <p className="text-xs text-red-300">{cleanupResult.error ?? "Cleanup failed."}</p>
        ) : null}
      </div>
    </section>
  );
}

type NewsApiRetentionResult = NewsRetentionStatus & { mode?: string; reason?: string };

function MetricMini({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900/40 px-2 py-2">
      <p className="font-mono text-[10px] uppercase text-zinc-500">{label}</p>
      <p className="mt-1 font-mono text-sm text-zinc-100">{value}</p>
    </div>
  );
}

function AddSourcePanel({
  disabled,
  loading,
  result,
  onSubmit,
}: {
  disabled?: boolean;
  loading: boolean;
  result: { status: string; error?: string; validation?: { entry_count: number } } | null;
  onSubmit: (params: { feed_url: string; name?: string; priority?: number; enabled?: boolean }) => void;
}) {
  const [feedUrl, setFeedUrl] = useState("");
  const [name, setName] = useState("");
  const [priority, setPriority] = useState("100");

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-950/40">
      <div className="border-b border-zinc-800 px-4 py-3">
        <h2 className="text-sm font-semibold text-zinc-100">Add RSS/Atom</h2>
        <p className="mt-0.5 text-xs text-zinc-500">Validated custom feeds only. Arbitrary HTML scraping stays disabled.</p>
      </div>
      <form
        className="space-y-3 p-4"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit({
            feed_url: feedUrl,
            name: name.trim() || undefined,
            priority: Number(priority) || 100,
            enabled: true,
          });
        }}
      >
        <label className="block space-y-1">
          <span className="font-mono text-[11px] uppercase text-zinc-500">Feed URL</span>
          <Input
            type="url"
            value={feedUrl}
            disabled={disabled || loading}
            placeholder="https://example.com/feed.xml"
            onChange={(event) => setFeedUrl(event.currentTarget.value)}
          />
        </label>
        <label className="block space-y-1">
          <span className="font-mono text-[11px] uppercase text-zinc-500">Name</span>
          <Input
            value={name}
            disabled={disabled || loading}
            placeholder="Optional"
            onChange={(event) => setName(event.currentTarget.value)}
          />
        </label>
        <div className="grid grid-cols-[1fr_auto] items-end gap-2">
          <label className="block space-y-1">
            <span className="font-mono text-[11px] uppercase text-zinc-500">Priority</span>
            <Input
              type="number"
              min={1}
              max={1000}
              value={priority}
              disabled={disabled || loading}
              mono
              onChange={(event) => setPriority(event.currentTarget.value)}
            />
          </label>
          <Button
            type="submit"
            size="sm"
            variant="primary"
            loading={loading}
            disabled={disabled || loading || !feedUrl.trim()}
          >
            Add
          </Button>
        </div>
        {result?.status === "success" ? (
          <p className="text-xs text-emerald-300">
            Source validated. {result.validation?.entry_count ?? 0} feed item
            {(result.validation?.entry_count ?? 0) === 1 ? "" : "s"} found.
          </p>
        ) : result?.status === "error" ? (
          <p className="text-xs text-red-300">{result.error ?? "Feed validation failed."}</p>
        ) : null}
      </form>
    </section>
  );
}

function RunsPanel({
  runs,
  loading,
}: {
  runs: Array<{
    run_id: string;
    status: string;
    started_at: string;
    articles_seen: number;
    articles_inserted: number;
    error_count: number;
  }>;
  loading: boolean;
}) {
  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-950/40">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">Collection Runs</h2>
          <p className="mt-0.5 text-xs text-zinc-500">Recent refresh diagnostics and source failure isolation.</p>
        </div>
        <span className="font-mono text-[11px] uppercase text-zinc-500">{runs.length} recent</span>
      </div>
      <div>
        {loading ? (
          <div className="p-4">
            <StateBanner variant="loading" title="Loading runs" size="dense" />
          </div>
        ) : runs.length === 0 ? (
          <div className="p-4">
            <StateBanner variant="empty" title="No refresh history" size="dense" />
          </div>
        ) : (
          <div className="divide-y divide-zinc-800">
            {runs.map((run) => (
              <div key={run.run_id} className="grid gap-2 px-4 py-3 text-xs md:grid-cols-[160px_minmax(0,1fr)_auto] md:items-center">
                <p className="font-mono text-zinc-300">{formatDate(run.started_at)}</p>
                <div className="min-w-0 text-zinc-500">
                  <span className="font-mono text-zinc-300">{run.articles_inserted}</span> inserted
                  <span className="mx-2 text-zinc-700">·</span>
                  <span className="font-mono text-zinc-300">{run.articles_seen}</span> seen
                  <span className="mx-2 text-zinc-700">·</span>
                  <span className={run.error_count ? "font-mono text-red-300" : "font-mono text-zinc-300"}>
                    {run.error_count}
                  </span>{" "}
                  errors
                </div>
                <StatusPill status={run.status} />
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function ContentStatus({ status, paywall }: { status: string; paywall?: string | null }) {
  const label = paywall === "paywalled" ? "paywalled" : status.replaceAll("_", " ");
  return (
    <span className="rounded border border-zinc-700 px-1.5 py-0.5 font-mono text-[11px] text-zinc-400">
      {label}
    </span>
  );
}

function PriorityPill({ priority }: { priority: string }) {
  const tone =
    priority === "Critical"
      ? "border-red-700 text-red-300"
      : priority === "High"
        ? "border-amber-700 text-amber-300"
        : "border-zinc-700 text-zinc-400";
  return (
    <span className={`rounded border px-1.5 py-0.5 font-mono text-[11px] uppercase ${tone}`}>
      {priority}
    </span>
  );
}

function StatusPill({ status }: { status: string }) {
  const tone =
    status === "success" || status === "not_modified"
      ? "border-emerald-700 text-emerald-300"
      : status === "error"
        ? "border-red-700 text-red-300"
        : status === "running"
          ? "border-sky-700 text-sky-300"
          : "border-zinc-700 text-zinc-400";
  return (
    <span className={`rounded border px-1.5 py-0.5 font-mono text-[11px] uppercase ${tone}`}>
      {status.replaceAll("_", " ")}
    </span>
  );
}

function plainArticleSummary(summary: string | null | undefined) {
  if (!summary) return "";
  return summary
    .replace(/Original source resolved from aggregator URL\./gi, " ")
    .replace(/Aggregator article URL was not resolved\./gi, " ")
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, " ")
    .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/\s+/g, " ")
    .trim();
}

function buildEditorialFrontPage(
  sections: NewsOverviewSection[],
  topArticles: NewsArticle[],
): EditorialFrontPageModel {
  const bySection = new Map(sections.map((section) => [section.section_id, section.items]));
  const critical = bySection.get("critical_news") ?? [];
  const topMarket = bySection.get("top_market_news") ?? topArticles;
  const macro = bySection.get("macro_watch") ?? [];
  const companies = bySection.get("my_companies") ?? [];
  const sectors = bySection.get("my_sectors") ?? [];
  const keywords = bySection.get("keyword_alerts") ?? [];
  const used = new Set<string>();
  const usedStoryKeys = new Set<string>();
  const sourceCounts = new Map<string, number>();
  const topicCounts = new Map<string, number>();

  const markUsed = (article: NewsArticle) => {
    const sourceKey = article.source_id || article.source_name;
    const topicKey = editorialTopicKey(article);
    const storyKey = editorialStoryKey(article);
    used.add(article.article_id);
    usedStoryKeys.add(storyKey);
    sourceCounts.set(sourceKey, (sourceCounts.get(sourceKey) ?? 0) + 1);
    topicCounts.set(topicKey, (topicCounts.get(topicKey) ?? 0) + 1);
  };

  const take = (items: NewsArticle[], limit: number, options: { maxPerSource?: number; maxPerTopic?: number } = {}) => {
    const result: NewsArticle[] = [];
    const deferred: NewsArticle[] = [];
    const accept = (article: NewsArticle) => {
      if (used.has(article.article_id)) return;
      if (usedStoryKeys.has(editorialStoryKey(article))) return;
      const sourceKey = article.source_id || article.source_name;
      const topicKey = editorialTopicKey(article);
      const sourceCount = sourceCounts.get(sourceKey) ?? 0;
      const topicCount = topicCounts.get(topicKey) ?? 0;
      if (
        (options.maxPerSource && sourceCount >= options.maxPerSource) ||
        (options.maxPerTopic && topicCount >= options.maxPerTopic)
      ) {
        deferred.push(article);
        return;
      }
      markUsed(article);
      result.push(article);
    };
    for (const article of items) {
      if (result.length >= limit) break;
      accept(article);
    }
    for (const article of deferred) {
      if (result.length >= limit) break;
      if (used.has(article.article_id)) continue;
      if (usedStoryKeys.has(editorialStoryKey(article))) continue;
      markUsed(article);
      result.push(article);
    }
    return result;
  };

  const lead = take(critical, 1)[0] ?? take(topMarket, 1)[0] ?? null;
  const secondary = take(topMarket, 3, { maxPerSource: 2, maxPerTopic: 1 });
  const criticalStrip = take(critical, 3, { maxPerSource: 2, maxPerTopic: 1 });

  return {
    lead,
    secondary,
    critical: criticalStrip,
    macro: take(macro, 4, { maxPerSource: 2, maxPerTopic: 2 }),
    companies: take(companies, 4, { maxPerSource: 2, maxPerTopic: 2 }),
    sectors: take(sectors, 5, { maxPerSource: 2, maxPerTopic: 2 }),
    keywords: take(keywords, 5, { maxPerSource: 2, maxPerTopic: 2 }),
  };
}

function editorialStoryKey(article: NewsArticle) {
  return normalizeEditorialText(article.title)
    .replace(/\b(google|news|rss|noticias|brasil|brazil)\b/g, " ")
    .split(/\s+/)
    .filter((word) => word.length > 2)
    .slice(0, 8)
    .join(" ");
}

function editorialTopicKey(article: NewsArticle) {
  return normalizeEditorialText(article.title)
    .split(/\s+/)
    .filter((word) => word.length > 3)
    .slice(0, 5)
    .join(" ");
}

function normalizeEditorialText(value: string) {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function summarizeSources(sources: NewsSource[]) {
  return sources.reduce(
    (acc, source) => {
      if (Boolean(source.enabled)) acc.enabled += 1;
      if (source.last_status === "success" || source.last_status === "not_modified") {
        acc.healthy += 1;
      }
      return acc;
    },
    { enabled: 0, healthy: 0 },
  );
}

function filterArticles(
  articles: NewsArticle[],
  filters: {
    searchText: string;
    showSavedOnly: boolean;
    showReadLaterOnly: boolean;
  },
) {
  const search = filters.searchText.trim().toLowerCase();
  return articles.filter((article) => {
    if (filters.showSavedOnly && !Boolean(article.saved)) return false;
    if (filters.showReadLaterOnly && !Boolean(article.read_later)) return false;
    if (!search) return true;
    const haystack = [
      article.title,
      article.source_name,
      article.summary,
      article.original_url,
      article.canonical_url,
      article.notes,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(search);
  });
}

function refreshLabel(status: NewsRefreshStatus | null) {
  if (!status) return "—";
  return status.status;
}

function refreshDetail(status: NewsRefreshStatus | null) {
  if (!status) return "status unavailable";
  if (status.status === "running") {
    return `${status.completed_sources ?? 0}/${status.source_count ?? 0} sources`;
  }
  if (status.error_count) return `${status.error_count} errors`;
  return status.finished_at ? formatDate(status.finished_at) : "idle";
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  if (value < 1024) return `${Math.round(value)} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
