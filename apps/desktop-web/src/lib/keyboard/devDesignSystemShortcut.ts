export const DEV_DESIGN_SYSTEM_PATH = "/dev/design-system";

type ShortcutEvent = Pick<KeyboardEvent, "altKey" | "ctrlKey" | "key" | "metaKey" | "shiftKey">;

export function resolveDevDesignSystemShortcut(event: ShortcutEvent): string | null {
  return event.key.toLowerCase() === "d" && event.ctrlKey && event.altKey && !event.metaKey && !event.shiftKey
    ? DEV_DESIGN_SYSTEM_PATH
    : null;
}
