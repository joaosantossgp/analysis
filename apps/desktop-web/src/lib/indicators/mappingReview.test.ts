import { describe, expect, it } from "vitest";

import type { AssetMappingEntry } from "@/lib/bridge/types";

import {
  NEW_CUSTOM_OWNER_VALUE,
  assetMatchesMappingSourceFilter,
  buildInitialMappingDraft,
  buildMappingUpdateParams,
  getMappingDraftValidation,
  ownerValueForAsset,
} from "./mappingReview";

const autoAsset: AssetMappingEntry = {
  id: "plant-1",
  type: "plant",
  name: "UHE Example",
  sub_name: "SE/CO",
  mapped_cvm: 1001,
  custom_owner_name: null,
  company_name: "CPFL Energia",
  ticker: "CPFE3",
  mapping_source: "auto",
  review_notes: null,
  stats: "100 MW",
};

const customAsset: AssetMappingEntry = {
  ...autoAsset,
  id: "plant-2",
  mapped_cvm: null,
  custom_owner_name: "Private Owner",
  company_name: "Private Owner",
  ticker: "",
  mapping_source: "manual",
  review_notes: "Confirmed from source file.",
};

describe("mapping review draft helpers", () => {
  it("starts the editor from the asset's current mapping and review notes", () => {
    expect(ownerValueForAsset(autoAsset)).toBe("cvm:1001");
    expect(buildInitialMappingDraft(customAsset)).toEqual({
      targetValue: "custom:Private Owner",
      customOwnerName: "",
      reviewNotes: "Confirmed from source file.",
    });
  });

  it("requires a review note before saving an auditable mapping change", () => {
    const draft = {
      targetValue: "cvm:2002",
      customOwnerName: "",
      reviewNotes: "   ",
    };

    expect(getMappingDraftValidation(autoAsset, draft)).toEqual({
      canSave: false,
      hasChanges: true,
      message: "Add a review note before saving the manual mapping.",
    });
  });

  it("builds a CVM company override payload with a trimmed review note", () => {
    const draft = {
      targetValue: "cvm:2002",
      customOwnerName: "",
      reviewNotes: "  Verified against company release.  ",
    };

    expect(getMappingDraftValidation(autoAsset, draft).canSave).toBe(true);
    expect(buildMappingUpdateParams(autoAsset, draft)).toEqual({
      assetId: "plant-1",
      assetType: "plant",
      cdCvm: 2002,
      customOwnerName: null,
      reviewNotes: "Verified against company release.",
    });
  });

  it("builds custom owner and unresolved review payloads without fake IDs", () => {
    expect(
      buildMappingUpdateParams(autoAsset, {
        targetValue: NEW_CUSTOM_OWNER_VALUE,
        customOwnerName: "  State Grid Brazil  ",
        reviewNotes: "Owner is not a listed CVM company.",
      }),
    ).toEqual({
      assetId: "plant-1",
      assetType: "plant",
      cdCvm: null,
      customOwnerName: "State Grid Brazil",
      reviewNotes: "Owner is not a listed CVM company.",
    });

    expect(
      buildMappingUpdateParams(autoAsset, {
        targetValue: "",
        customOwnerName: "",
        reviewNotes: "Current owner could not be verified.",
      }),
    ).toEqual({
      assetId: "plant-1",
      assetType: "plant",
      cdCvm: null,
      customOwnerName: null,
      reviewNotes: "Current owner could not be verified.",
    });
  });

  it("treats manually cleared mappings as unlinked in review filters", () => {
    const manuallyClearedAsset: AssetMappingEntry = {
      ...autoAsset,
      mapped_cvm: null,
      custom_owner_name: null,
      company_name: "",
      ticker: "",
      mapping_source: "manual",
      review_notes: "Could not verify the owner.",
    };

    expect(assetMatchesMappingSourceFilter(manuallyClearedAsset, "unmapped")).toBe(true);
    expect(assetMatchesMappingSourceFilter(manuallyClearedAsset, "manual")).toBe(true);
    expect(assetMatchesMappingSourceFilter(manuallyClearedAsset, "auto")).toBe(false);
  });
});
