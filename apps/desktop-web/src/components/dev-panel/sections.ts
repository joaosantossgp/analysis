import type { ComponentType } from "react";

export type DevPanelSectionProps = {
  /** Closes the dev panel, e.g. before navigating away. */
  closePanel: () => void;
};

export type DevPanelSection = {
  id: string;
  /** Position in the panel, ascending. Leave gaps so a new section fits between two others. */
  order: number;
  Component: ComponentType<DevPanelSectionProps>;
};

/**
 * Every `sections/*Section.tsx` file that exports `section` is part of the
 * panel. Adding a section means adding one file: no shared list to edit.
 */
const modules = import.meta.glob<{ section: DevPanelSection }>("./sections/*Section.tsx", { eager: true });

export const DEV_PANEL_SECTIONS: DevPanelSection[] = Object.values(modules)
  .map((module) => module.section)
  .sort((a, b) => a.order - b.order);
