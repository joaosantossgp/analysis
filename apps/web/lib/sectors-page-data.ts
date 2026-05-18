import {
  fetchSectorDetail,
  fetchSectorDirectory,
  fetchSubSectorDetail,
  getUserFacingErrorMessage,
  type SectorDetail,
  type SectorDirectory,
} from "./api.ts";

import {
  coerceSectorTab,
  resolveSectorYear,
  type SectorPageTab,
} from "./sectors-params.ts";

export type { SectorPageTab };

type SectorLoaders = {
  fetchDirectory?: () => Promise<SectorDirectory>;
  fetchDetail?: (slug: string, year?: number) => Promise<SectorDetail | null>;
};

export type SectorsPageData = {
  directory: SectorDirectory | null;
  directoryError: string | null;
};

export type SectorDetailPageData = {
  detail: SectorDetail | null;
  currentTab: SectorPageTab;
  detailError: string | null;
};

export async function loadSectorsPageData(
  loaders: SectorLoaders = {},
): Promise<SectorsPageData> {
  const fetchDirectory = loaders.fetchDirectory ?? fetchSectorDirectory;

  try {
    return {
      directory: await fetchDirectory(),
      directoryError: null,
    };
  } catch (error) {
    return {
      directory: null,
      directoryError: getUserFacingErrorMessage(error),
    };
  }
}

export async function loadSectorDetailPageData(
  sectorSlug: string,
  rawYear: string | undefined,
  rawTab: string | undefined,
  loaders: SectorLoaders = {},
): Promise<SectorDetailPageData> {
  const fetchDetail = loaders.fetchDetail ?? fetchSectorDetail;
  return loadDetailPageData(
    (year) => fetchDetail(sectorSlug, year),
    rawYear,
    rawTab,
  );
}

export async function loadSubSectorDetailPageData(
  sectorSlug: string,
  subIndustrySlug: string,
  rawYear: string | undefined,
  rawTab: string | undefined,
  loaders: {
    fetchDetail?: (
      sectorSlug: string,
      subIndustrySlug: string,
      year?: number,
    ) => Promise<SectorDetail | null>;
  } = {},
): Promise<SectorDetailPageData> {
  const fetchDetail = loaders.fetchDetail ?? fetchSubSectorDetail;
  return loadDetailPageData(
    (year) => fetchDetail(sectorSlug, subIndustrySlug, year),
    rawYear,
    rawTab,
  );
}

async function loadDetailPageData(
  fetchDetail: (year?: number) => Promise<SectorDetail | null>,
  rawYear: string | undefined,
  rawTab: string | undefined,
): Promise<SectorDetailPageData> {
  const currentTab = coerceSectorTab(rawTab);

  try {
    const latestDetail = await fetchDetail();

    if (!latestDetail) {
      return {
        detail: null,
        currentTab,
        detailError: null,
      };
    }

    const resolvedYear = resolveSectorYear(
      latestDetail.available_years,
      rawYear,
      latestDetail.selected_year,
    );

    if (resolvedYear === latestDetail.selected_year) {
      return {
        detail: latestDetail,
        currentTab,
        detailError: null,
      };
    }

    let yearScopedDetail: SectorDetail | null = null;

    try {
      yearScopedDetail = await fetchDetail(resolvedYear);
    } catch {
      yearScopedDetail = null;
    }

    return {
      detail: yearScopedDetail ?? latestDetail,
      currentTab,
      detailError: null,
    };
  } catch (error) {
    return {
      detail: null,
      currentTab,
      detailError: getUserFacingErrorMessage(error),
    };
  }
}
