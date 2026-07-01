import type { AssetMappingEntry } from "@/lib/bridge/types";

export const NEW_CUSTOM_OWNER_VALUE = "action:new-custom";

export type MappingDraft = {
  targetValue: string;
  customOwnerName: string;
  reviewNotes: string;
};

export type MappingDraftValidation = {
  canSave: boolean;
  hasChanges: boolean;
  message: string | null;
};

export type MappingUpdateParams = {
  assetId: string;
  assetType: "distributor" | "plant";
  cdCvm: number | null;
  customOwnerName: string | null;
  reviewNotes: string | null;
};

export type MappingSourceFilter = "all" | "auto" | "manual" | "unmapped";

export function ownerValueForAsset(asset: AssetMappingEntry): string {
  if (asset.mapped_cvm) return `cvm:${asset.mapped_cvm}`;
  if (asset.custom_owner_name) return `custom:${asset.custom_owner_name}`;
  return "";
}

export function buildInitialMappingDraft(asset: AssetMappingEntry): MappingDraft {
  return {
    targetValue: ownerValueForAsset(asset),
    customOwnerName: "",
    reviewNotes: asset.review_notes ?? "",
  };
}

export function getMappingDraftValidation(
  asset: AssetMappingEntry,
  draft: MappingDraft,
): MappingDraftValidation {
  const target = normalizeDraftTarget(draft);
  const currentTarget = ownerValueForAsset(asset);
  const currentNotes = asset.review_notes?.trim() ?? "";
  const draftNotes = draft.reviewNotes.trim();
  const hasChanges = target !== currentTarget || draftNotes !== currentNotes;

  if (!hasChanges) {
    return {
      canSave: false,
      hasChanges,
      message: "No mapping changes to save.",
    };
  }

  if (draft.targetValue === NEW_CUSTOM_OWNER_VALUE && !draft.customOwnerName.trim()) {
    return {
      canSave: false,
      hasChanges,
      message: "Enter a custom owner name before saving.",
    };
  }

  if (!draftNotes) {
    return {
      canSave: false,
      hasChanges,
      message: "Add a review note before saving the manual mapping.",
    };
  }

  return { canSave: true, hasChanges, message: null };
}

export function buildMappingUpdateParams(
  asset: AssetMappingEntry,
  draft: MappingDraft,
): MappingUpdateParams {
  const target = normalizeDraftTarget(draft);
  const reviewNotes = draft.reviewNotes.trim() || null;

  if (target.startsWith("cvm:")) {
    return {
      assetId: asset.id,
      assetType: asset.type,
      cdCvm: Number(target.slice(4)),
      customOwnerName: null,
      reviewNotes,
    };
  }

  if (target.startsWith("custom:")) {
    return {
      assetId: asset.id,
      assetType: asset.type,
      cdCvm: null,
      customOwnerName: target.slice(7).trim(),
      reviewNotes,
    };
  }

  return {
    assetId: asset.id,
    assetType: asset.type,
    cdCvm: null,
    customOwnerName: null,
    reviewNotes,
  };
}

export function assetMatchesMappingSourceFilter(
  asset: AssetMappingEntry,
  filter: MappingSourceFilter,
): boolean {
  if (filter === "all") return true;
  if (filter === "unmapped") return !asset.mapped_cvm && !asset.custom_owner_name;
  return asset.mapping_source === filter;
}

function normalizeDraftTarget(draft: MappingDraft): string {
  if (draft.targetValue === NEW_CUSTOM_OWNER_VALUE) {
    const customOwnerName = draft.customOwnerName.trim();
    return customOwnerName ? `custom:${customOwnerName}` : NEW_CUSTOM_OWNER_VALUE;
  }
  return draft.targetValue;
}
