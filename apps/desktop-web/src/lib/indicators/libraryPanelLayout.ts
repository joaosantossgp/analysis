export const DEFAULT_LIBRARY_PANEL_WIDTH = 420;
export const MIN_LIBRARY_PANEL_WIDTH = 360;
export const MAX_LIBRARY_PANEL_WIDTH = 760;

export function clampLibraryPanelWidth(width: number): number {
  if (!Number.isFinite(width)) return DEFAULT_LIBRARY_PANEL_WIDTH;
  return Math.min(MAX_LIBRARY_PANEL_WIDTH, Math.max(MIN_LIBRARY_PANEL_WIDTH, Math.round(width)));
}

export function calculateLibraryPanelDragWidth({
  startWidth,
  startX,
  currentX,
}: {
  startWidth: number;
  startX: number;
  currentX: number;
}): number {
  return clampLibraryPanelWidth(startWidth + startX - currentX);
}

type PanelRect = {
  top?: number;
  right?: number;
  bottom?: number;
};

export function calculateLibraryPanelViewportBounds({
  viewportWidth,
  viewportHeight,
  contentRect,
  mainRect,
  tableRect,
  gutter = 16,
}: {
  viewportWidth: number;
  viewportHeight: number;
  contentRect: PanelRect;
  mainRect: PanelRect;
  tableRect: PanelRect;
  gutter?: number;
}): { top: number; right: number; bottom: number } {
  const safeTop = (mainRect.top ?? 0) + gutter;
  const safeBottom = Math.max(0, viewportHeight - (mainRect.bottom ?? viewportHeight) + gutter);
  const top = Math.max(tableRect.top ?? safeTop, safeTop);
  const right = Math.max(0, viewportWidth - (contentRect.right ?? viewportWidth));
  const bottom = Math.max(viewportHeight - (tableRect.bottom ?? viewportHeight), safeBottom);

  return {
    top: Math.round(top),
    right: Math.round(right),
    bottom: Math.round(bottom),
  };
}
