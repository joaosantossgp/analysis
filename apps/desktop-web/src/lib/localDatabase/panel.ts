/** Lets Home and empty states open the shell's Data panel without owning it. */
export const OPEN_DATA_PANEL_EVENT = "cvm:open-data-panel";

export function openDataPanel(): void {
  window.dispatchEvent(new Event(OPEN_DATA_PANEL_EVENT));
}
