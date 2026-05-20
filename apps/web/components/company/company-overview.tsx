import { CompanyAnalysisPanelLazy } from "@/components/company/company-analysis-panel-lazy";
import { CompanyMarketSidebar } from "@/components/company/company-market-sidebar";
import type { CompanyInfo, KPIBundle } from "@/lib/api";
import { buildCompanyDashboardModel } from "@/lib/company-dashboard";

type CompanyOverviewProps = {
  company: CompanyInfo;
  bundle: KPIBundle;
};

export function CompanyOverview({
  company,
  bundle,
}: CompanyOverviewProps) {
  const model = buildCompanyDashboardModel(bundle);

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 lg:gap-8">
      <div className="flex flex-col gap-6 lg:col-span-8">
        <CompanyAnalysisPanelLazy model={model} />
      </div>

      <div className="lg:col-span-4">
        <CompanyMarketSidebar company={company} />
      </div>
    </div>
  );
}
