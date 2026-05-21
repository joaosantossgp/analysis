"use client";

import {
  BarChart3Icon,
  DatabaseIcon,
  FileTextIcon,
  LayersIcon,
  SearchIcon,
  TrendingUpIcon,
  type LucideIcon,
} from "lucide-react";

type Capability = {
  icon: LucideIcon;
  title: string;
  detail: string;
  metric: string;
};

const capabilities: Capability[] = [
  {
    icon: SearchIcon,
    title: "Busca inteligente",
    detail: "Nome, ticker ou codigo CVM",
    metric: "663 empresas",
  },
  {
    icon: FileTextIcon,
    title: "Demonstracoes CVM",
    detail: "DRE, BPA, BPP e DFC navegaveis",
    metric: "4 visoes",
  },
  {
    icon: BarChart3Icon,
    title: "KPIs auditaveis",
    detail: "Margens, ROE, liquidez e eficiencia",
    metric: "60+ KPIs",
  },
  {
    icon: LayersIcon,
    title: "Setores GICS",
    detail: "Setor e sub-setor separados",
    metric: "11 hubs",
  },
];

const previewRows = [
  { label: "Receita liquida", value: "R$ 48.2B", trend: "+12.4%", width: "88%" },
  { label: "Margem EBIT", value: "24.8%", trend: "+3.1 p.p.", width: "72%" },
  { label: "ROE anual", value: "18.6%", trend: "+2.8 p.p.", width: "64%" },
];

export function BentoFeatures() {
  return (
    <section className="mx-auto w-full max-w-6xl">
      <div className="mb-8 text-center">
        <p className="eyebrow mb-3">Recursos</p>
        <h2 className="font-heading text-[clamp(1.75rem,4vw,2.5rem)] font-medium tracking-[-0.035em] text-foreground">
          Tudo que voce precisa para analisar
        </h2>
        <p className="mx-auto mt-3 max-w-xl text-base leading-relaxed text-muted-foreground">
          Uma leitura unica para descobrir, filtrar e aprofundar companhias abertas brasileiras.
        </p>
      </div>

      <div className="grid overflow-hidden rounded-[1.75rem] border border-white/10 bg-[var(--background)] shadow-[0_34px_110px_-50px_rgba(7,18,15,0.72)] lg:grid-cols-[1.05fr_0.95fr]">
        <div className="border-b border-white/10 p-6 sm:p-8 lg:border-b-0 lg:border-r">
          <div className="mb-7 flex items-center justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-teal-200/80">
                Painel CVM
              </p>
              <h3 className="mt-2 font-heading text-2xl font-medium text-foreground">
                Leitura financeira pronta para decisao
              </h3>
            </div>
            <DatabaseIcon className="h-8 w-8 text-teal-200" aria-hidden="true" />
          </div>

          <div className="space-y-4">
            {previewRows.map((row) => (
              <div key={row.label} className="rounded-xl border border-white/10 bg-white/[0.035] p-4">
                <div className="mb-3 flex items-center justify-between gap-4">
                  <span className="text-sm text-muted-foreground">{row.label}</span>
                  <span className="text-sm font-semibold text-emerald-200">{row.trend}</span>
                </div>
                <div className="flex items-end justify-between gap-4">
                  <span className="font-heading text-2xl font-medium text-foreground">{row.value}</span>
                  <div className="h-2 w-32 rounded-full bg-white/10">
                    <div className="h-full rounded-full bg-teal-300" style={{ width: row.width }} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid content-center gap-3 p-6 sm:p-8">
          {capabilities.map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.title} className="grid grid-cols-[2.75rem_1fr_auto] items-center gap-4 rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <div className="grid h-11 w-11 place-items-center rounded-lg bg-teal-300/10 text-teal-200">
                  <Icon className="h-5 w-5" aria-hidden="true" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-foreground">{item.title}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">{item.detail}</p>
                </div>
                <div className="hidden text-right text-sm font-semibold text-foreground sm:block">
                  {item.metric}
                </div>
              </div>
            );
          })}
          <div className="mt-3 flex items-center gap-2 rounded-xl border border-emerald-300/20 bg-emerald-300/10 px-4 py-3 text-sm text-emerald-100">
            <TrendingUpIcon className="h-4 w-4" aria-hidden="true" />
            <span>Experiencia responsiva para leitura, comparacao e decisao.</span>
          </div>
        </div>
      </div>
    </section>
  );
}
