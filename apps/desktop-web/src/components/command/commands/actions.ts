import { openStatusPath } from "@/lib/api/appStatus";

import type { Command } from "../CommandRegistry";

/**
 * App-level actions that don't navigate. Currently: reveal local folders
 * (output / data / database / logs / cache) via the bridge. Browser-mode
 * activation surfaces a user-readable error in the toast/log path; the
 * command still ranks in the palette so users discover what's available
 * in the desktop build.
 *
 * `onError` is invoked with a Promise rejection so callers can surface the
 * problem (e.g. via toast in UX-9). For now we console.warn so dev sees it.
 */

type ActionDeps = {
  onError?: (err: unknown) => void;
};

function safeRun(promise: Promise<unknown>, onError?: (err: unknown) => void): void {
  promise.catch((err) => {
    if (onError) onError(err);
    else console.warn("[command]", err);
  });
}

export function buildActionCommands(deps: ActionDeps = {}): Command[] {
  const reveal = (kind: "output" | "data" | "database" | "logs" | "cache", label: string): Command => ({
    id: `action:open:${kind}`,
    group: "actions",
    glyph: "action",
    label: `Abrir pasta ${label}`,
    secondary: kind,
    keywords: ["open", "reveal", "folder", "pasta", kind],
    run: () => safeRun(openStatusPath(kind), deps.onError),
  });

  return [
    reveal("output", "de exportações"),
    reveal("data", "de dados"),
    reveal("database", "do banco SQLite"),
    reveal("logs", "de logs"),
    reveal("cache", "de cache"),
  ];
}
