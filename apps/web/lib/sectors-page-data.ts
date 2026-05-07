import {
  fetchSectorDetail,
  fetchSectorDirectory,
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
  const currentTab = coerceSectorTab(rawTab);

  try {
    const latestDetail = await fetchDetail(sectorSlug);

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
      yearScopedDetail = await fetchDetail(sectorSlug, resolvedYear);
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
