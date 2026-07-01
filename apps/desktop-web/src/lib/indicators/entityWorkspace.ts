import type {
  AssetMappingEntry,
  ConglomerateEntry,
  CvmRegistryEntry,
} from "@/lib/bridge/types";

export type MappingReviewTone = "success" | "warning" | "neutral";

export type EntityWorkspaceSummary = {
  totalAssets: number;
  mappedAssets: number;
  unmappedAssets: number;
  autoLinks: number;
  manualLinks: number;
  customOwnerLinks: number;
  linkedCompanies: number;
  listedPortfolios: number;
  customPortfolios: number;
  distributorCoverage: string;
  plantCoverage: string;
};

export type PortfolioRow = {
  ownerKey: string;
  companyName: string;
  isListed: boolean;
  cdCvm: number | null;
  ticker: string | null;
  cnpj: string | null;
  setorCvm: string | null;
  gicsSector: string | null;
  distributorsCount: number;
  plantsCount: number;
  totalAssets: number;
  totalCapacityMw: number;
  totalGenerationMwmed: number;
  manualLinks: number;
  autoLinks: number;
  customOwnerLinks: number;
};

export type AssetMappingReviewState = {
  label: string;
  tone: MappingReviewTone;
  detail: string;
  needsReview: boolean;
};

export function summarizeEntityWorkspace(
  assets: AssetMappingEntry[],
  companies: CvmRegistryEntry[],
  conglomerates: ConglomerateEntry[],
): EntityWorkspaceSummary {
  const totalDistributors = assets.filter((asset) => asset.type === "distributor").length;
  const mappedDistributors = assets.filter(
    (asset) => asset.type === "distributor" && isMapped(asset),
  ).length;
  const totalPlants = assets.filter((asset) => asset.type === "plant").length;
  const mappedPlants = assets.filter((asset) => asset.type === "plant" && isMapped(asset)).length;

  return {
    totalAssets: assets.length,
    mappedAssets: assets.filter(isMapped).length,
    unmappedAssets: assets.filter((asset) => !isMapped(asset)).length,
    autoLinks: assets.filter((asset) => asset.mapping_source === "auto").length,
    manualLinks: assets.filter((asset) => asset.mapping_source === "manual").length,
    customOwnerLinks: assets.filter((asset) => Boolean(asset.custom_owner_name)).length,
    linkedCompanies: companies.filter(
      (company) => company.mapped_distributors > 0 || company.mapped_plants > 0,
    ).length,
    listedPortfolios: conglomerates.filter(
      (company) => company.is_listed && linkedAssetCount(company) > 0,
    ).length,
    customPortfolios: conglomerates.filter(
      (company) => !company.is_listed && linkedAssetCount(company) > 0,
    ).length,
    distributorCoverage: `${mappedDistributors} / ${totalDistributors}`,
    plantCoverage: `${mappedPlants} / ${totalPlants}`,
  };
}

export function buildPortfolioRows(
  conglomerates: ConglomerateEntry[],
  assets: AssetMappingEntry[],
): PortfolioRow[] {
  return conglomerates
    .map((company) => {
      const companyAssets = assets.filter((asset) =>
        company.is_listed
          ? asset.mapped_cvm === company.cd_cvm
          : asset.custom_owner_name === company.company_name,
      );
      const totalAssets = companyAssets.length;

      return {
        ownerKey: company.is_listed
          ? `cvm:${company.cd_cvm ?? "unknown"}`
          : `custom:${company.company_name}`,
        companyName: company.company_name,
        isListed: company.is_listed,
        cdCvm: company.cd_cvm,
        ticker: company.ticker_b3,
        cnpj: company.cnpj,
        setorCvm: company.setor_cvm,
        gicsSector: company.gics_sector,
        distributorsCount: company.distributors_count,
        plantsCount: company.plants_count,
        totalAssets,
        totalCapacityMw: company.total_capacity_mw,
        totalGenerationMwmed: company.total_generation_mwmed,
        manualLinks: companyAssets.filter((asset) => asset.mapping_source === "manual").length,
        autoLinks: companyAssets.filter((asset) => asset.mapping_source === "auto").length,
        customOwnerLinks: companyAssets.filter((asset) => Boolean(asset.custom_owner_name)).length,
      };
    })
    .filter((row) => row.totalAssets > 0)
    .sort((a, b) => {
      if (b.totalAssets !== a.totalAssets) return b.totalAssets - a.totalAssets;
      if (b.totalCapacityMw !== a.totalCapacityMw) return b.totalCapacityMw - a.totalCapacityMw;
      return a.companyName.localeCompare(b.companyName);
    });
}

export function getAssetMappingReviewState(
  asset: AssetMappingEntry,
): AssetMappingReviewState {
  if (!isMapped(asset)) {
    return {
      label: "Needs review",
      tone: "neutral",
      detail: "No company or custom owner is linked.",
      needsReview: true,
    };
  }

  if (asset.custom_owner_name) {
    return {
      label: "Custom owner",
      tone: "warning",
      detail: asset.review_notes ?? "Linked to a non-listed/custom owner; no review note recorded.",
      needsReview: false,
    };
  }

  if (asset.mapping_source === "manual") {
    return {
      label: "Manual override",
      tone: "warning",
      detail: asset.review_notes ?? "User-adjusted relationship; no review note recorded.",
      needsReview: false,
    };
  }

  return {
    label: "Auto linked",
    tone: "success",
    detail: "Inferred relationship; confidence is not recorded.",
    needsReview: false,
  };
}

export function getPriorityReviewQueue(
  assets: AssetMappingEntry[],
  limit = 8,
): AssetMappingEntry[] {
  return [...assets]
    .sort((a, b) => {
      const aNeedsReview = isMapped(a) ? 1 : 0;
      const bNeedsReview = isMapped(b) ? 1 : 0;
      if (aNeedsReview !== bNeedsReview) return aNeedsReview - bNeedsReview;
      if (a.type !== b.type) return a.type.localeCompare(b.type);
      return a.name.localeCompare(b.name);
    })
    .slice(0, limit);
}

function linkedAssetCount(company: ConglomerateEntry): number {
  return company.distributors_count + company.plants_count;
}

function isMapped(asset: AssetMappingEntry): boolean {
  return Boolean(asset.mapped_cvm || asset.custom_owner_name);
}
