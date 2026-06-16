import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { StateBanner } from "@/components/feedback/StateBanner";
import {
  applyNewsClassificationCorrection,
  addCustomNewsSource,
  cleanupNewsExtractedContent,
  fetchNewsArticleClassification,
  fetchNewsArticleContent,
  fetchNewsArticles,
  fetchNewsCompanyScope,
  fetchNewsCollectionRuns,
  fetchNewsOverview,
  fetchNewsRefreshStatus,
  fetchNewsRetentionStatus,
  fetchNewsSources,
  refreshNewsSources,
  saveNewsRetentionPolicy,
  setNewsCompanyScopeOverride,
  setNewsSourceEnabled,
  setNewsSourcePriority,
  updateNewsArticleState,
} from "@/lib/api/news";
import type {
  ApplyNewsClassificationCorrectionParams,
  ApplyNewsClassificationCorrectionResult,
  NewsArticle,
  NewsArticleClassificationResponse,
  NewsArticleContentResponse,
  NewsCompanyScopeResponse,
  NewsOverviewSection,
  NewsRefreshStatus,
  NewsRetentionStatus,
  SaveNewsRetentionPolicyParams,
  SaveNewsRetentionPolicyResult,
  CleanupNewsExtractedContentResult,
  SetNewsCompanyScopeOverrideParams,
  SetNewsCompanyScopeOverrideResult,
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
  const [selectedArticleId, setSelectedArticleId] = useState<string | null>(null);
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
  const refreshStatusQuery = useQuery({
    queryKey: ["news", "refresh-status"],
    queryFn: fetchNewsRefreshStatus,
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 2_000 : 15_000,
  });
  const classificationQuery = useQuery({
    queryKey: ["news", "article-classification", selectedArticleId],
    queryFn: () => fetchNewsArticleClassification(selectedArticleId ?? ""),
    enabled: Boolean(selectedArticleId),
  });
  const articleContentQuery = useQuery({
    queryKey: ["news", "article-content", selectedArticleId],
    queryFn: () => fetchNewsArticleContent(selectedArticleId ?? ""),
    enabled: Boolean(selectedArticleId),
  });

  const refreshMutation = useMutation({
    mutationFn: refreshNewsSources,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["news"] });
    },
  });
  const sourceEnabledMutation = useMutation({
    mutationFn: setNewsSourceEnabled,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["news", "sources"] });
    },
  });
  const sourcePriorityMutation = useMutation({
    mutationFn: setNewsSourcePriority,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["news", "sources"] });
    },
  });
  const addSourceMutation = useMutation({
    mutationFn: addCustomNewsSource,
    onSuccess: (payload) => {
      if (payload.status === "success") {
        void queryClient.invalidateQueries({ queryKey: ["news", "sources"] });
      }
    },
  });
  const articleStateMutation = useMutation({
    mutationFn: updateNewsArticleState,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["news", "articles"] });
    },
  });
  const classificationCorrectionMutation = useMutation({
    mutationFn: applyNewsClassificationCorrection,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["news", "article-classification", selectedArticleId] });
      void queryClient.invalidateQueries({ queryKey: ["news", "articles"] });
      void queryClient.invalidateQueries({ queryKey: ["news", "overview"] });
    },
  });
  const companyScopeMutation = useMutation({
    mutationFn: setNewsCompanyScopeOverride,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["news", "company-scope"] });
      void queryClient.invalidateQueries({ queryKey: ["news", "overview"] });
    },
  });
  const saveRetentionMutation = useMutation({
    mutationFn: saveNewsRetentionPolicy,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["news", "retention"] });
    },
  });
  const cleanupRetentionMutation = useMutation({
    mutationFn: cleanupNewsExtractedContent,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["news"] });
    },
  });

  const articles = articlesQuery.data?.items ?? [];
  const overviewSections = overviewQuery.data?.sections ?? [];
  const overviewArticles = useMemo(
    () => overviewSections.flatMap((section) => section.items),
    [overviewSections],
  );
  const sources = sourcesQuery.data?.items ?? [];
  const runs = runsQuery.data?.items ?? [];
  const browserReason =
    articlesQuery.data?.mode === "browser" ? articlesQuery.data.reason : null;
  const loadError =
    articlesQuery.error ?? sourcesQuery.error ?? runsQuery.error ?? refreshStatusQuery.error;

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
  const selectedArticle = useMemo(
    () =>
      filteredArticles.find((article) => article.article_id === selectedArticleId) ??
      overviewArticles.find((article) => article.article_id === selectedArticleId) ??
      null,
    [filteredArticles, overviewArticles, selectedArticleId],
  );

  useEffect(() => {
    if (selectedArticleId && !selectedArticle) {
      setSelectedArticleId(null);
    }
  }, [selectedArticle, selectedArticleId]);

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
    <section className="space-y-4 p-6">
      {browserReason ? <StateBanner variant="browser-only" message={browserReason} /> : null}

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-wider text-zinc-500">
            Local News
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-zinc-100">News</h1>
          <p className="mt-1 max-w-3xl text-sm text-zinc-400">
            Financial news collected into the local News database with explicit source status.
          </p>
        </div>
        <div className="flex items-center gap-2">
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

      <div className="grid gap-3 md:grid-cols-4">
        <MetricTile label="Articles" value={articlesQuery.data?.total ?? 0} />
        <MetricTile label="Sources" value={sources.length} detail={`${sourceStats.enabled} enabled`} />
        <MetricTile label="Healthy" value={sourceStats.healthy} detail="successful or unchanged" />
        <MetricTile
          label="Refresh"
          value={refreshLabel(refreshStatus)}
          detail={refreshDetail(refreshStatus)}
        />
      </div>

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

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <main className="min-w-0 rounded-lg border border-zinc-800 bg-zinc-950/40">
          {view === "top" ? (
            <NewsOverview
              sections={overviewSections}
              loading={overviewQuery.isLoading}
              error={overviewQuery.error ?? overviewQuery.data?.error}
              selectedArticleId={selectedArticleId}
              onSelect={setSelectedArticleId}
            />
          ) : null}
          <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
            <div>
              <h2 className="text-sm font-semibold text-zinc-100">
                {view === "latest" ? "Latest" : "Top News"}
              </h2>
              <p className="mt-0.5 text-xs text-zinc-500">
                {view === "latest"
                  ? "Chronological local feed"
                  : "Explainable ranking area"}
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
                  selectedArticleId={selectedArticleId}
                  disabled={articleStateMutation.isPending}
                  onSelect={setSelectedArticleId}
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

        <aside className="space-y-4">
          <ArticleDetailPanel
            article={selectedArticle}
            classification={classificationQuery.data ?? null}
            classificationLoading={classificationQuery.isFetching}
            classificationError={classificationQuery.error}
            content={articleContentQuery.data ?? null}
            contentLoading={articleContentQuery.isFetching}
            contentError={articleContentQuery.error}
            correctionLoading={classificationCorrectionMutation.isPending}
            correctionResult={classificationCorrectionMutation.data ?? null}
            onCorrect={(params) => classificationCorrectionMutation.mutate(params)}
          />
          <SourceHealthPanel
            sources={sources}
            loading={sourcesQuery.isLoading}
            disabled={articlesQuery.data?.mode === "browser"}
            pendingSourceId={
              sourceEnabledMutation.isPending
                ? sourceEnabledMutation.variables?.source_id ?? null
                : sourcePriorityMutation.isPending
                  ? sourcePriorityMutation.variables?.source_id ?? null
                  : null
            }
            onToggleSource={(source, enabled) =>
              sourceEnabledMutation.mutate({ source_id: source.source_id, enabled })
            }
            onPriorityChange={(source, priority) =>
              sourcePriorityMutation.mutate({ source_id: source.source_id, priority })
            }
          />
          <NewsCompanyScopePanel
            scope={companyScopeQuery.data ?? null}
            loading={companyScopeQuery.isLoading}
            disabled={articlesQuery.data?.mode === "browser" || companyScopeMutation.isPending}
            result={companyScopeMutation.data ?? null}
            onSetOverride={(params) => companyScopeMutation.mutate(params)}
          />
          <NewsRetentionPanel
            status={retentionQuery.data ?? null}
            loading={retentionQuery.isLoading}
            disabled={articlesQuery.data?.mode === "browser"}
            saving={saveRetentionMutation.isPending}
            cleaning={cleanupRetentionMutation.isPending}
            saveResult={saveRetentionMutation.data ?? null}
            cleanupResult={cleanupRetentionMutation.data ?? null}
            onSave={(params) => saveRetentionMutation.mutate(params)}
            onCleanup={(dryRun) => cleanupRetentionMutation.mutate({ dry_run: dryRun })}
          />
          <AddSourcePanel
            disabled={articlesQuery.data?.mode === "browser"}
            loading={addSourceMutation.isPending}
            result={addSourceMutation.data ?? null}
            onSubmit={(params) => addSourceMutation.mutate(params)}
          />
          <RunsPanel runs={runs} loading={runsQuery.isLoading} />
        </aside>
      </div>
    </section>
  );
}

function NewsOverview({
  sections,
  loading,
  error,
  selectedArticleId,
  onSelect,
}: {
  sections: NewsOverviewSection[];
  loading: boolean;
  error: unknown;
  selectedArticleId: string | null;
  onSelect: (articleId: string) => void;
}) {
  if (loading) {
    return (
      <div className="border-b border-zinc-800 p-4">
        <StateBanner variant="loading" title="Loading overview" size="dense" />
      </div>
    );
  }
  if (error) {
    return (
      <div className="border-b border-zinc-800 p-4">
        <StateBanner
          variant="warning"
          title="Overview unavailable"
          message={error instanceof Error ? error.message : String(error)}
          size="dense"
        />
      </div>
    );
  }
  if (sections.length === 0) return null;

  return (
    <div className="border-b border-zinc-800 p-4">
      <div className="grid gap-3 lg:grid-cols-2">
        {sections.map((section) => (
          <OverviewSectionCard
            key={section.section_id}
            section={section}
            selectedArticleId={selectedArticleId}
            onSelect={onSelect}
          />
        ))}
      </div>
    </div>
  );
}

function OverviewSectionCard({
  section,
  selectedArticleId,
  onSelect,
}: {
  section: NewsOverviewSection;
  selectedArticleId: string | null;
  onSelect: (articleId: string) => void;
}) {
  const critical = section.section_id === "critical_news";
  return (
    <section className={`rounded-md border p-3 ${critical ? "border-red-900/70 bg-red-950/10" : "border-zinc-800 bg-zinc-900/30"}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">{section.title}</h3>
          <p className="mt-0.5 text-xs leading-4 text-zinc-500">{section.reason}</p>
        </div>
        <span className="font-mono text-[11px] uppercase text-zinc-500">
          {section.items.length}
        </span>
      </div>
      <div className="mt-3 space-y-2">
        {section.items.length === 0 ? (
          <p className="rounded border border-zinc-800 bg-zinc-950/40 px-2 py-2 text-xs text-zinc-500">
            No matching local articles.
          </p>
        ) : (
          section.items.map((article) => (
            <OverviewArticleLine
              key={article.article_id}
              article={article}
              selected={article.article_id === selectedArticleId}
              onSelect={onSelect}
            />
          ))
        )}
      </div>
    </section>
  );
}

function OverviewArticleLine({
  article,
  selected,
  onSelect,
}: {
  article: NewsArticle;
  selected: boolean;
  onSelect: (articleId: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(article.article_id)}
      className={`w-full rounded border px-2 py-2 text-left ${
        selected ? "border-amber-600/70 bg-amber-500/5" : "border-zinc-800 bg-zinc-950/40 hover:border-zinc-700"
      }`}
    >
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <span className="font-mono text-amber-200">{article.source_name}</span>
        <time className="font-mono text-zinc-500">{formatDate(article.published_at ?? article.discovered_at)}</time>
        <PriorityPill priority={article.priority_level ?? "Normal"} />
      </div>
      <p className="mt-1 line-clamp-2 text-xs font-medium leading-4 text-zinc-200">
        {article.title}
      </p>
    </button>
  );
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

function MetricTile({
  label,
  value,
  detail,
}: {
  label: string;
  value: string | number;
  detail?: string;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-3">
      <p className="font-mono text-[11px] uppercase tracking-wider text-zinc-500">{label}</p>
      <p className="mt-1 font-mono text-lg text-zinc-100">{value}</p>
      {detail ? <p className="mt-1 text-xs text-zinc-500">{detail}</p> : null}
    </div>
  );
}

function ArticleList({
  articles,
  selectedArticleId,
  disabled,
  onSelect,
  onUpdate,
}: {
  articles: NewsArticle[];
  selectedArticleId: string | null;
  disabled?: boolean;
  onSelect: (articleId: string) => void;
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
          selected={article.article_id === selectedArticleId}
          disabled={disabled}
          onSelect={onSelect}
          onUpdate={onUpdate}
        />
      ))}
    </div>
  );
}

function ArticleRow({
  article,
  selected,
  disabled,
  onSelect,
  onUpdate,
}: {
  article: NewsArticle;
  selected: boolean;
  disabled?: boolean;
  onSelect: (articleId: string) => void;
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
      className={`rounded-md border px-3 py-3 first:mt-0 last:mb-0 ${
        selected ? "border-amber-600/70 bg-amber-500/5" : "border-transparent"
      } ${isRead ? "opacity-75" : ""}`}
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
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="xs"
          variant={isRead ? "ghost" : "secondary"}
          disabled={disabled}
          onClick={() => onUpdate({ article_id: article.article_id, read: !isRead })}
        >
          {isRead ? "Unread" : "Read"}
        </Button>
        <Button
          type="button"
          size="xs"
          variant={selected ? "primary" : "secondary"}
          onClick={() => onSelect(article.article_id)}
        >
          Details
        </Button>
        <Button
          type="button"
          size="xs"
          variant={isSaved ? "primary" : "secondary"}
          disabled={disabled}
          onClick={() => onUpdate({ article_id: article.article_id, saved: !isSaved })}
        >
          {isSaved ? "Saved" : "Save"}
        </Button>
        <Button
          type="button"
          size="xs"
          variant={isReadLater ? "primary" : "secondary"}
          disabled={disabled}
          onClick={() => onUpdate({ article_id: article.article_id, read_later: !isReadLater })}
        >
          Later
        </Button>
        <Button
          type="button"
          size="xs"
          variant="ghost"
          disabled={disabled}
          onClick={() => onUpdate({ article_id: article.article_id, hidden: true })}
        >
          Hide
        </Button>
      </div>
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
    </article>
  );
}

function ArticleDetailPanel({
  article,
  classification,
  classificationLoading,
  classificationError,
  content,
  contentLoading,
  contentError,
  correctionLoading,
  correctionResult,
  onCorrect,
}: {
  article: NewsArticle | null;
  classification: NewsArticleClassificationResponse | null;
  classificationLoading: boolean;
  classificationError: unknown;
  content: NewsArticleContentResponse | null;
  contentLoading: boolean;
  contentError: unknown;
  correctionLoading: boolean;
  correctionResult: ApplyNewsClassificationCorrectionResult | null;
  onCorrect: (params: ApplyNewsClassificationCorrectionParams) => void;
}) {
  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-950/40">
      <div className="border-b border-zinc-800 px-4 py-3">
        <h2 className="text-sm font-semibold text-zinc-100">Article Details</h2>
      </div>
      <div className="p-4">
        {!article ? (
          <StateBanner
            variant="empty"
            title="No article selected"
            message="Select Details on a feed item to inspect source, timestamps, availability, and local state."
            size="dense"
          />
        ) : (
          <div className="space-y-4">
            <div>
              <p className="font-mono text-[11px] uppercase text-amber-200">
                {article.source_name}
              </p>
              <h3 className="mt-1 text-sm font-semibold leading-5 text-zinc-100">
                {article.title}
              </h3>
              {article.summary ? (
                <p className="mt-2 text-xs leading-5 text-zinc-400">{article.summary}</p>
              ) : null}
            </div>

            <div className="flex flex-wrap gap-2">
              <ContentStatus status={article.content_status} paywall={article.paywall_status} />
              {article.read ? <StatusPill status="read" /> : <StatusPill status="unread" />}
              {article.saved ? <StatusPill status="saved" /> : null}
              {article.read_later ? <StatusPill status="read_later" /> : null}
              {article.hidden ? <StatusPill status="hidden" /> : null}
            </div>

            <dl className="space-y-2 text-xs">
              <DetailRow label="Published" value={formatDate(article.published_at)} />
              <DetailRow label="Discovered" value={formatDate(article.discovered_at)} />
              <DetailRow label="Fetched" value={formatDate(article.fetched_at)} />
              <DetailRow label="Source ID" value={article.source_id} mono />
              <DetailLink label="Original URL" href={article.original_url} />
              <DetailLink label="Canonical URL" href={article.canonical_url} />
            </dl>

            <div className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
              <p className="font-mono text-[11px] uppercase text-zinc-500">Availability</p>
              <p className="mt-1 text-xs text-zinc-300">{availabilityLabel(article)}</p>
            </div>

            <ArticleContentPanel
              article={article}
              content={content}
              loading={contentLoading}
              error={contentError}
            />

            <ClassificationPanel
              articleId={article.article_id}
              classification={classification}
              loading={classificationLoading}
              error={classificationError}
              correctionLoading={correctionLoading}
              correctionResult={correctionResult}
              onCorrect={onCorrect}
            />
            <ScorePanel article={article} classification={classification} />

            {article.notes ? (
              <div className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
                <p className="font-mono text-[11px] uppercase text-zinc-500">Note</p>
                <p className="mt-1 whitespace-pre-wrap text-xs text-zinc-300">{article.notes}</p>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </section>
  );
}

function ClassificationPanel({
  articleId,
  classification,
  loading,
  error,
  correctionLoading,
  correctionResult,
  onCorrect,
}: {
  articleId: string;
  classification: NewsArticleClassificationResponse | null;
  loading: boolean;
  error: unknown;
  correctionLoading: boolean;
  correctionResult: ApplyNewsClassificationCorrectionResult | null;
  onCorrect: (params: ApplyNewsClassificationCorrectionParams) => void;
}) {
  if (loading) {
    return <StateBanner variant="loading" title="Loading classification" size="dense" />;
  }
  if (error || classification?.error) {
    return (
      <StateBanner
        variant="warning"
        title="Classification unavailable"
        message={
          classification?.error ??
          (error instanceof Error ? error.message : "Could not load article classification.")
        }
        size="dense"
      />
    );
  }
  if (
    !classification ||
    (classification.keywords.length === 0 &&
      classification.topics.length === 0 &&
      classification.event_types.length === 0 &&
      classification.companies.length === 0 &&
      classification.sectors.length === 0)
  ) {
    return (
      <div className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
        <p className="font-mono text-[11px] uppercase text-zinc-500">Classification</p>
        <p className="mt-1 text-xs text-zinc-400">No deterministic matches recorded.</p>
      </div>
    );
  }
  return (
    <div className="space-y-3 rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <p className="font-mono text-[11px] uppercase text-zinc-500">Classification</p>
      <CompanyMatchGroup
        items={classification.companies.map((item) => ({
          key: String(item.cd_cvm),
          cdCvm: item.cd_cvm,
          label: `CVM ${item.cd_cvm}`,
          reason: item.match_reason,
        }))}
        disabled={correctionLoading}
        onRemove={(item) =>
          onCorrect({
            article_id: articleId,
            target_type: "company",
            target_id: String(item.cdCvm),
            action: "remove",
            user_value: { match_reason: "Removed from article by user" },
          })
        }
      />
      <SectorMatchGroup
        items={classification.sectors.map((item) => ({
          key: `${item.parent_sector_slug ?? "root"}-${item.sector_slug}`,
          sectorSlug: item.sector_slug,
          to: item.parent_sector_slug
            ? `/setores/${item.parent_sector_slug}/${item.sector_slug}`
            : `/setores/${item.sector_slug}`,
          label: item.parent_sector_name
            ? `${item.parent_sector_name}: ${item.sector_name}`
            : item.sector_name,
          reason: item.match_reason,
        }))}
        disabled={correctionLoading}
        onRemove={(item) =>
          onCorrect({
            article_id: articleId,
            target_type: "sector",
            target_id: item.sectorSlug,
            action: "remove",
            user_value: { match_reason: "Removed from article by user" },
          })
        }
      />
      <TagGroup
        label="Keywords"
        items={classification.keywords.map((item) => ({
          key: `${item.keyword_rule_id}-${item.matched_term}`,
          targetId: item.keyword_rule_id,
          targetType: "keyword",
          label: `${item.group_name}: ${item.matched_term}`,
          reason: item.match_reason,
        }))}
        disabled={correctionLoading}
        onRemove={(item) =>
          onCorrect({
            article_id: articleId,
            target_type: item.targetType,
            target_id: item.targetId,
            action: "remove",
            user_value: { match_reason: "Removed from article by user" },
          })
        }
      />
      <TagGroup
        label="Topics"
        items={classification.topics.map((item) => ({
          key: item.topic_id,
          targetId: item.topic_id,
          targetType: "topic",
          label: `${item.topic_type}: ${item.label}`,
          reason: item.match_reason,
        }))}
        disabled={correctionLoading}
        onRemove={(item) =>
          onCorrect({
            article_id: articleId,
            target_type: item.targetType,
            target_id: item.targetId,
            action: "remove",
            user_value: { match_reason: "Removed from article by user" },
          })
        }
      />
      <TagGroup
        label="Events"
        items={classification.event_types.map((item) => ({
          key: item.event_type_id,
          targetId: item.event_type_id,
          targetType: "event_type",
          label: item.sub_event ? `${item.category}: ${item.sub_event}` : item.category,
          reason: item.match_reason,
        }))}
        disabled={correctionLoading}
        onRemove={(item) =>
          onCorrect({
            article_id: articleId,
            target_type: item.targetType,
            target_id: item.targetId,
            action: "remove",
            user_value: { match_reason: "Removed from article by user" },
          })
        }
      />
      <ManualCorrectionForm
        articleId={articleId}
        disabled={correctionLoading}
        result={correctionResult}
        onCorrect={onCorrect}
      />
      <CorrectionHistory corrections={classification.corrections ?? []} />
    </div>
  );
}

function ArticleContentPanel({
  article,
  content,
  loading,
  error,
}: {
  article: NewsArticle;
  content: NewsArticleContentResponse | null;
  loading: boolean;
  error: unknown;
}) {
  if (loading) {
    return <StateBanner variant="loading" title="Loading local content" size="dense" />;
  }
  if (error || content?.error) {
    return (
      <StateBanner
        variant="warning"
        title="Local content unavailable"
        message={content?.error ?? (error instanceof Error ? error.message : "Could not load local article content.")}
        size="dense"
      />
    );
  }
  if (!content?.available || !content.content_text) {
    return (
      <div className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="font-mono text-[11px] uppercase text-zinc-500">Local content</p>
            <p className="mt-1 text-xs text-zinc-400">{localContentMissingLabel(article)}</p>
          </div>
          <a
            href={article.original_url}
            target="_blank"
            rel="noreferrer"
            className="shrink-0 text-xs text-amber-200 hover:text-amber-100"
          >
            Open source
          </a>
        </div>
      </div>
    );
  }
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-mono text-[11px] uppercase text-zinc-500">Local content</p>
          <p className="mt-1 text-[11px] text-zinc-500">
            {content.content_format ?? "text"} · {formatBytes(content.storage_bytes ?? 0)} · extracted {formatDate(content.extracted_at)}
          </p>
        </div>
        <a
          href={article.original_url}
          target="_blank"
          rel="noreferrer"
          className="text-xs text-amber-200 hover:text-amber-100"
        >
          Source
        </a>
      </div>
      <div className="mt-3 max-h-80 overflow-auto rounded border border-zinc-800 bg-zinc-950/60 p-3">
        <p className="whitespace-pre-wrap text-xs leading-5 text-zinc-300">{content.content_text}</p>
      </div>
    </div>
  );
}

function ScorePanel({
  article,
  classification,
}: {
  article: NewsArticle;
  classification: NewsArticleClassificationResponse | null;
}) {
  const score = classification?.score;
  const total = score?.total_score ?? article.relevance_score ?? 0;
  const priority = score?.priority_level ?? article.priority_level ?? "Normal";
  const components = score?.components ?? article.relevance_components ?? {};
  const reasons = score?.reasons ?? article.relevance_reasons ?? [];
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="font-mono text-[11px] uppercase text-zinc-500">Priority</p>
        <PriorityPill priority={priority} />
      </div>
      <p className="mt-1 font-mono text-xs text-zinc-300">Score {Number(total).toFixed(2)}</p>
      {Object.keys(components).length > 0 ? (
        <div className="mt-2 grid grid-cols-2 gap-1 text-[11px] text-zinc-400">
          {Object.entries(components).map(([key, value]) => (
            <div key={key} className="flex justify-between gap-2 rounded border border-zinc-800 px-2 py-1">
              <span>{key.replaceAll("_", " ")}</span>
              <span className="font-mono text-zinc-300">{Number(value).toFixed(2)}</span>
            </div>
          ))}
        </div>
      ) : null}
      {reasons.length > 0 ? (
        <ul className="mt-2 space-y-1 text-[11px] leading-4 text-zinc-500">
          {reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function ManualCorrectionForm({
  articleId,
  disabled,
  result,
  onCorrect,
}: {
  articleId: string;
  disabled: boolean;
  result: ApplyNewsClassificationCorrectionResult | null;
  onCorrect: (params: ApplyNewsClassificationCorrectionParams) => void;
}) {
  const [targetType, setTargetType] = useState("company");
  const [targetId, setTargetId] = useState("");
  const [sectorName, setSectorName] = useState("");
  const [reason, setReason] = useState("Manual user correction");

  return (
    <form
      className="rounded border border-zinc-800 bg-zinc-950/50 p-3"
      onSubmit={(event) => {
        event.preventDefault();
        const cleanTargetId = targetId.trim();
        if (!cleanTargetId) return;
        onCorrect({
          article_id: articleId,
          target_type: targetType,
          target_id: cleanTargetId,
          action: "add",
          user_value: {
            match_reason: reason.trim() || "Manual user correction",
            sector_name: targetType === "sector" ? sectorName.trim() : undefined,
          },
        });
      }}
    >
      <p className="font-mono text-[11px] uppercase text-zinc-500">Manual correction</p>
      <div className="mt-2 grid gap-2 md:grid-cols-[120px_1fr]">
        <label className="space-y-1">
          <span className="font-mono text-[11px] uppercase text-zinc-500">Type</span>
          <select
            value={targetType}
            disabled={disabled}
            onChange={(event) => setTargetType(event.currentTarget.value)}
            className="h-8 w-full rounded-md border border-zinc-700 bg-zinc-950 px-2 text-sm text-zinc-100 outline-none focus:border-amber-500"
          >
            <option value="company">Company</option>
            <option value="sector">Sector</option>
            <option value="topic">Topic</option>
            <option value="event_type">Event type</option>
            <option value="keyword">Keyword</option>
          </select>
        </label>
        <label className="space-y-1">
          <span className="font-mono text-[11px] uppercase text-zinc-500">ID</span>
          <Input
            value={targetId}
            disabled={disabled}
            placeholder="CVM code, sector slug, topic ID, event ID, or keyword rule ID"
            onChange={(event) => setTargetId(event.currentTarget.value)}
          />
        </label>
      </div>
      {targetType === "sector" ? (
        <label className="mt-2 block space-y-1">
          <span className="font-mono text-[11px] uppercase text-zinc-500">Sector name</span>
          <Input
            value={sectorName}
            disabled={disabled}
            placeholder="Required for manual sector links"
            onChange={(event) => setSectorName(event.currentTarget.value)}
          />
        </label>
      ) : null}
      <label className="mt-2 block space-y-1">
        <span className="font-mono text-[11px] uppercase text-zinc-500">Reason</span>
        <Input
          value={reason}
          disabled={disabled}
          onChange={(event) => setReason(event.currentTarget.value)}
        />
      </label>
      <div className="mt-2 flex items-center justify-between gap-3">
        <Button
          type="submit"
          size="xs"
          variant="secondary"
          loading={disabled}
          disabled={disabled || !targetId.trim() || (targetType === "sector" && !sectorName.trim())}
        >
          Add
        </Button>
        {result?.status === "error" ? (
          <p className="text-xs text-red-300">{result.error ?? "Correction failed."}</p>
        ) : result?.status === "success" ? (
          <p className="text-xs text-emerald-300">Correction saved.</p>
        ) : null}
      </div>
    </form>
  );
}

function CorrectionHistory({
  corrections,
}: {
  corrections: NonNullable<NewsArticleClassificationResponse["corrections"]>;
}) {
  if (corrections.length === 0) return null;
  return (
    <div className="rounded border border-zinc-800 bg-zinc-950/50 p-3">
      <p className="font-mono text-[11px] uppercase text-zinc-500">Correction history</p>
      <div className="mt-2 space-y-2">
        {corrections.slice(0, 8).map((correction) => (
          <div key={correction.correction_id} className="text-[11px] leading-4 text-zinc-400">
            <p>
              <span className="font-mono uppercase text-zinc-300">{correction.correction_action}</span>{" "}
              {correction.target_type} <span className="font-mono">{correction.target_id}</span>
            </p>
            <p className="text-zinc-500">
              {formatDate(correction.created_at)}
              {correction.original_match_reason ? ` · previous: ${correction.original_match_reason}` : ""}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

function SectorMatchGroup({
  items,
  disabled,
  onRemove,
}: {
  items: Array<{ key: string; sectorSlug: string; to: string; label: string; reason: string }>;
  disabled?: boolean;
  onRemove?: (item: { key: string; sectorSlug: string; to: string; label: string; reason: string }) => void;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="font-mono text-[11px] uppercase text-zinc-500">Sectors</p>
      <div className="mt-1 space-y-1">
        {items.map((item) => (
          <div key={item.key} className="rounded border border-zinc-800 bg-zinc-950/50 px-2 py-1.5">
            <div className="flex items-start justify-between gap-2">
              <Link to={item.to} className="text-xs font-medium text-amber-200 hover:text-amber-100">
                {item.label}
              </Link>
              {onRemove ? (
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => onRemove(item)}
                  className="font-mono text-[10px] uppercase text-zinc-500 hover:text-red-300 disabled:opacity-50"
                >
                  Remove
                </button>
              ) : null}
            </div>
            <p className="mt-0.5 text-[11px] leading-4 text-zinc-500">{item.reason}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function CompanyMatchGroup({
  items,
  disabled,
  onRemove,
}: {
  items: Array<{ key: string; cdCvm: number; label: string; reason: string }>;
  disabled?: boolean;
  onRemove?: (item: { key: string; cdCvm: number; label: string; reason: string }) => void;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="font-mono text-[11px] uppercase text-zinc-500">Companies</p>
      <div className="mt-1 space-y-1">
        {items.map((item) => (
          <div key={item.key} className="rounded border border-zinc-800 bg-zinc-950/50 px-2 py-1.5">
            <div className="flex items-start justify-between gap-2">
              <Link
                to={`/empresas/${item.cdCvm}`}
                className="text-xs font-medium text-amber-200 hover:text-amber-100"
              >
                {item.label}
              </Link>
              {onRemove ? (
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => onRemove(item)}
                  className="font-mono text-[10px] uppercase text-zinc-500 hover:text-red-300 disabled:opacity-50"
                >
                  Remove
                </button>
              ) : null}
            </div>
            <p className="mt-0.5 text-[11px] leading-4 text-zinc-500">{item.reason}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function TagGroup({
  label,
  items,
  disabled,
  onRemove,
}: {
  label: string;
  items: Array<{ key: string; label: string; reason: string; targetId?: string; targetType?: string }>;
  disabled?: boolean;
  onRemove?: (item: { key: string; label: string; reason: string; targetId: string; targetType: string }) => void;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="font-mono text-[11px] uppercase text-zinc-500">{label}</p>
      <div className="mt-1 space-y-1">
        {items.map((item) => (
          <div key={item.key} className="rounded border border-zinc-800 bg-zinc-950/50 px-2 py-1.5">
            <div className="flex items-start justify-between gap-2">
              <p className="text-xs font-medium text-zinc-200">{item.label}</p>
              <TagRemoveButton item={item} disabled={disabled} onRemove={onRemove} />
            </div>
            <p className="mt-0.5 text-[11px] leading-4 text-zinc-500">{item.reason}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function TagRemoveButton({
  item,
  disabled,
  onRemove,
}: {
  item: { key: string; label: string; reason: string; targetId?: string; targetType?: string };
  disabled?: boolean;
  onRemove?: (item: { key: string; label: string; reason: string; targetId: string; targetType: string }) => void;
}) {
  if (!onRemove || !item.targetId || !item.targetType) return null;
  const removableItem = { ...item, targetId: item.targetId, targetType: item.targetType };
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onRemove(removableItem)}
      className="font-mono text-[10px] uppercase text-zinc-500 hover:text-red-300 disabled:opacity-50"
    >
      Remove
    </button>
  );
}

function DetailRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="grid grid-cols-[92px_minmax(0,1fr)] gap-3">
      <dt className="font-mono uppercase text-zinc-500">{label}</dt>
      <dd className={`${mono ? "font-mono" : ""} min-w-0 break-words text-zinc-300`}>{value}</dd>
    </div>
  );
}

function DetailLink({ label, href }: { label: string; href?: string | null }) {
  if (!href) return <DetailRow label={label} value="-" />;
  return (
    <div className="grid grid-cols-[92px_minmax(0,1fr)] gap-3">
      <dt className="font-mono uppercase text-zinc-500">{label}</dt>
      <dd className="min-w-0">
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          className="break-words text-xs text-amber-200 hover:text-amber-100"
        >
          {href}
        </a>
      </dd>
    </div>
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
      <div className="border-b border-zinc-800 px-4 py-3">
        <h2 className="text-sm font-semibold text-zinc-100">Sources</h2>
      </div>
      <div className="p-4">
        {loading ? (
          <StateBanner variant="loading" title="Loading sources" size="dense" />
        ) : sources.length === 0 ? (
          <StateBanner variant="empty" title="No sources" size="dense" />
        ) : (
          <div className="space-y-3">
            {sources.map((source) => (
              <SourceCard
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

function SourceCard({
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
    <div className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-zinc-100">{source.name}</p>
                    <p className="mt-0.5 font-mono text-[11px] uppercase text-zinc-500">
                      {source.reliability_layer} · priority {source.priority}
                      {source.allow_content_storage ? " · local content eligible" : ""}
                    </p>
                  </div>
                  <StatusPill status={source.last_status ?? (source.enabled ? "pending" : "disabled")} />
                </div>
                {source.last_error ? (
                  <p className="mt-2 text-xs text-red-300">{source.last_error}</p>
                ) : null}
      <div className="mt-3 grid grid-cols-[1fr_auto] items-end gap-2">
        <label className="space-y-1">
          <span className="font-mono text-[11px] uppercase text-zinc-500">Priority</span>
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
        </label>
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

function NewsCompanyScopePanel({
  scope,
  loading,
  disabled,
  result,
  onSetOverride,
}: {
  scope: NewsApiScopeResult | null;
  loading: boolean;
  disabled?: boolean;
  result: SetNewsCompanyScopeOverrideResult | null;
  onSetOverride: (params: SetNewsCompanyScopeOverrideParams) => void;
}) {
  const [companyId, setCompanyId] = useState("");
  const [action, setAction] = useState<"include" | "exclude">("include");
  const [reason, setReason] = useState("News-specific company scope override");
  const overrides = scope?.overrides ?? [];

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
          Uses the current company universe{scope?.selected_preset ? ` (${scope.selected_preset})` : ""}.
          Overrides apply only to News.
        </p>
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
      <div className="border-b border-zinc-800 px-4 py-3">
        <h2 className="text-sm font-semibold text-zinc-100">Collection Runs</h2>
      </div>
      <div className="p-4">
        {loading ? (
          <StateBanner variant="loading" title="Loading runs" size="dense" />
        ) : runs.length === 0 ? (
          <StateBanner variant="empty" title="No refresh history" size="dense" />
        ) : (
          <div className="space-y-2">
            {runs.map((run) => (
              <div key={run.run_id} className="flex items-center justify-between gap-3 text-xs">
                <div>
                  <p className="font-mono text-zinc-300">{formatDate(run.started_at)}</p>
                  <p className="text-zinc-500">
                    {run.articles_inserted} inserted · {run.articles_seen} seen
                  </p>
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

function availabilityLabel(article: NewsArticle) {
  if (article.paywall_status === "paywalled") {
    return "Paywalled. Open externally; the app will not bypass access controls.";
  }
  switch (article.content_status) {
    case "full_text_available":
      return "Full text is available locally.";
    case "summary_available":
      return "Summary or feed snippet is available locally.";
    case "official_document":
      return "Official document metadata is available; eligible documents can be preserved.";
    case "external_only":
      return "External only. Open the original source to read.";
    case "extraction_failed":
      return "Metadata was stored, but content extraction failed.";
    case "offline_copy_available":
      return "An offline copy is available locally.";
    case "paywalled":
      return "Paywalled. Open externally; the app will not bypass access controls.";
    case "metadata_only":
    default:
      return "Metadata only. Open the original source to read.";
  }
}

function localContentMissingLabel(article: NewsArticle) {
  if (article.paywall_status === "paywalled" || article.content_status === "paywalled") {
    return "Paywalled content is not stored locally. Open the original source if you have access.";
  }
  if (article.content_status === "external_only") {
    return "This article is external only. CVMAnalytics keeps metadata and attribution locally.";
  }
  if (article.content_status === "metadata_only") {
    return "Only metadata is stored locally for this article.";
  }
  if (article.content_status === "summary_available") {
    return "Only the feed summary is stored locally.";
  }
  if (article.content_status === "extraction_failed") {
    return "Content extraction failed; metadata remains available.";
  }
  return "No local article body is currently stored.";
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
