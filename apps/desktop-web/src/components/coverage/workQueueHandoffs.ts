export type CoverageWorkQueueTask = {
  task_type?: string | null;
  cd_cvm?: number | string | null;
  reason?: string | null;
  severity?: string | null;
  source?: string | null;
  score_status?: string | null;
  updated_at?: string | null;
  created_at?: string | null;
};

export type CoverageWorkQueueHandoff = {
  supported: boolean;
  analystQuestion: string;
  evidenceSurface: string;
  actionLabel: string | null;
  destination: string | null;
  completionSignal: string;
  unsupportedReason: string | null;
};

export const SUPPORTED_COVERAGE_WORK_QUEUE_TYPES = [
  "missing_market_cap",
  "missing_liquidity",
  "missing_gics",
  "unassigned_owner",
  "incomplete_checklist",
  "checklist_gap",
  "news_mapping_unavailable",
  "news_gap",
  "news_db_unavailable",
] as const;

type SupportedCoverageWorkQueueType = (typeof SUPPORTED_COVERAGE_WORK_QUEUE_TYPES)[number];

type HandoffDefinition = {
  analystQuestion: string;
  evidenceSurface: string;
  actionLabel: string;
  completionSignal: string;
  destination: (task: CoverageWorkQueueTask) => string | null;
  requiresCompany?: boolean;
};

const HANDOFFS: Record<SupportedCoverageWorkQueueType, HandoffDefinition> = {
  missing_market_cap: {
    analystQuestion: "Is market-cap evidence available for coverage scoring?",
    evidenceSurface: "Settings Sources · Market caps (Yahoo Finance, unofficial)",
    actionLabel: "Open market caps",
    completionSignal:
      "Market-cap evidence becomes available for scoring, or the provider/snapshot failure remains visible.",
    destination: () => "/settings/sources",
  },
  missing_liquidity: {
    analystQuestion: "Is recent trading liquidity available for scoring?",
    evidenceSurface: "Company Overview market history",
    actionLabel: "Open market history",
    completionSignal:
      "The 30-day liquidity observation count reaches the scoring threshold, or the market-history refresh/ticker failure remains visible.",
    destination: (task) => companyRoute(task, ""),
    requiresCompany: true,
  },
  missing_gics: {
    analystQuestion: "Is the company sector classification usable for capacity and complexity scoring?",
    evidenceSurface: "Company Overview identity header",
    actionLabel: "Open company identity",
    completionSignal:
      "GICS sector and slug are populated, or the company refresh/metadata failure remains visible.",
    destination: (task) => companyRoute(task, ""),
    requiresCompany: true,
  },
  unassigned_owner: {
    analystQuestion: "Who owns the next research review for this company?",
    evidenceSurface: "Coverage Prioritization",
    actionLabel: "Assign owner",
    completionSignal:
      "An owner analyst is recorded for the company, or the save action returns an explicit rationale/failure state.",
    destination: () => "/empresas/coverage/prioritization",
  },
  incomplete_checklist: {
    analystQuestion: "Which required coverage deliverable is still incomplete?",
    evidenceSurface: "Company Coverage checklist",
    actionLabel: "Open checklist",
    completionSignal:
      "The required checklist item is marked complete with rationale, or the checklist save failure remains visible.",
    destination: (task) => companyRoute(task, "/coverage"),
    requiresCompany: true,
  },
  checklist_gap: {
    analystQuestion: "Which required coverage deliverable is still incomplete?",
    evidenceSurface: "Company Coverage checklist",
    actionLabel: "Open checklist",
    completionSignal:
      "The required checklist item is marked complete with rationale, or the checklist save failure remains visible.",
    destination: (task) => companyRoute(task, "/coverage"),
    requiresCompany: true,
  },
  news_mapping_unavailable: {
    analystQuestion: "Can local news evidence be associated with this company?",
    evidenceSurface: "Settings Sources",
    actionLabel: "Open source settings",
    completionSignal:
      "The company is mapped to local news evidence, or source configuration continues to show an explicit gap.",
    destination: () => "/settings/sources",
  },
  news_gap: {
    analystQuestion: "Is recent local news coverage available for this high-priority company?",
    evidenceSurface: "News workspace",
    actionLabel: "Open news",
    completionSignal:
      "Recent local articles appear for the company, or the source/RSS failure remains visible.",
    destination: () => "/news",
  },
  news_db_unavailable: {
    analystQuestion: "Is the local news database readable?",
    evidenceSurface: "News workspace",
    actionLabel: "Open news",
    completionSignal:
      "The news database loads successfully, or the unavailable database state remains explicit.",
    destination: () => "/news",
  },
};

export function resolveCoverageWorkQueueHandoff(
  task: CoverageWorkQueueTask,
  context: { universeId?: string | null } = {},
): CoverageWorkQueueHandoff {
  const taskType = normalizeTaskType(task.task_type);
  const definition = getHandoffDefinition(taskType);
  if (["news_gap", "news_mapping_unavailable", "news_db_unavailable"].includes(taskType)) {
    return unsupportedHandoff("News has been retired from the interface. Existing queue evidence and downloaded data are preserved.", definition ?? undefined);
  }


  if (!definition) {
    return unsupportedHandoff(
      `No supported workflow handoff exists yet for task type ${taskType || "unknown"}.`,
    );
  }

  if (definition.requiresCompany && getCompanyId(task) === null) {
    return unsupportedHandoff(
      "This handoff requires a company CVM id, but the queue item did not provide one.",
      definition,
    );
  }

  const destinationBase = definition.destination(task);
  return {
    supported: Boolean(destinationBase),
    analystQuestion: definition.analystQuestion,
    evidenceSurface: definition.evidenceSurface,
    actionLabel: destinationBase ? definition.actionLabel : null,
    destination: destinationBase ? withQueueContext(destinationBase, task, context) : null,
    completionSignal: definition.completionSignal,
    unsupportedReason: destinationBase ? null : "No supported destination exists for this queue item.",
  };
}

function getHandoffDefinition(taskType: string): HandoffDefinition | null {
  if ((SUPPORTED_COVERAGE_WORK_QUEUE_TYPES as readonly string[]).includes(taskType)) {
    return HANDOFFS[taskType as SupportedCoverageWorkQueueType];
  }
  return null;
}

function unsupportedHandoff(
  unsupportedReason: string,
  definition?: HandoffDefinition,
): CoverageWorkQueueHandoff {
  return {
    supported: false,
    analystQuestion: definition?.analystQuestion ?? "What analyst question should this queue reason trigger?",
    evidenceSurface: definition?.evidenceSurface ?? "No evidence surface assigned",
    actionLabel: null,
    destination: null,
    completionSignal: definition?.completionSignal ?? "No completion signal is defined for this queue reason yet.",
    unsupportedReason,
  };
}

function normalizeTaskType(value: string | null | undefined): string {
  return String(value ?? "").trim();
}

function getCompanyId(task: CoverageWorkQueueTask): number | null {
  const value = Number(task.cd_cvm);
  return Number.isFinite(value) && value > 0 ? value : null;
}

function companyRoute(task: CoverageWorkQueueTask, suffix: string): string | null {
  const cdCvm = getCompanyId(task);
  return cdCvm ? `/empresas/${cdCvm}${suffix}` : null;
}

function withQueueContext(
  destination: string,
  task: CoverageWorkQueueTask,
  context: { universeId?: string | null },
): string {
  const params = new URLSearchParams();
  params.set("from", "coverage-work-queue");
  if (context.universeId) params.set("universe_id", context.universeId);
  if (task.task_type) params.set("task_type", String(task.task_type));
  const cdCvm = getCompanyId(task);
  if (cdCvm) params.set("cd_cvm", String(cdCvm));
  if (task.reason) params.set("reason", task.reason);
  if (task.severity) params.set("severity", task.severity);
  if (task.source) params.set("source", task.source);
  if (task.score_status) params.set("score_status", task.score_status);
  const timestamp = task.updated_at ?? task.created_at;
  if (timestamp) params.set("timestamp", timestamp);
  const query = params.toString();
  return query ? `${destination}?${query}` : destination;
}
