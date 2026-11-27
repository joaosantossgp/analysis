export type DevPanelAction = "toggle" | "close";

export function devPanelOpenReducer(open: boolean, action: DevPanelAction): boolean {
  return action === "toggle" ? !open : false;
}

type KeyEvent = Pick<KeyboardEvent, "altKey" | "ctrlKey" | "key" | "metaKey" | "shiftKey">;

/** Ctrl+Shift+D toggles the dev panel; Escape closes it while open. Ctrl+Alt+D stays the design-system shortcut. */
export function resolveDevPanelKey(event: KeyEvent, open: boolean): DevPanelAction | null {
  if (event.altKey || event.metaKey) return null;
  if (event.key.toLowerCase() === "d" && event.ctrlKey && event.shiftKey) return "toggle";
  if (event.key === "Escape" && open && !event.ctrlKey && !event.shiftKey) return "close";
  return null;
}
