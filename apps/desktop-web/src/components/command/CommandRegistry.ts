/**
 * Command registry — shape of every command surfaced in the palette.
 *
 * Commands come from three sources:
 *   - Navigation (static routes)
 *   - Companies (dynamic, fetched lazily from the bridge)
 *   - Actions (refresh, export-folder, etc.)
 *
 * Each source contributes to a unified result list. The palette ranks all
 * commands by score (see `scoreCommand`) and renders the top N.
 */

export type CommandGroup = "navigation" | "companies" | "actions";

export type CommandGlyph = "route" | "company" | "action";

export type Command = {
  /** Stable unique id used for keying. */
  id: string;
  group: CommandGroup;
  glyph: CommandGlyph;
  /** Primary visible label (e.g. company name or route title). */
  label: string;
  /** Secondary text shown right of the label (CVM code, ticker, route URL). */
  secondary?: string;
  /** Optional keyboard hint shown on the right edge. */
  shortcut?: string;
  /** Search keywords beyond label/secondary. */
  keywords?: string[];
  /** Invoked when the user activates the command. */
  run: () => void;
};

/**
 * Score how well a command matches a query. Returns a number in [0, 100],
 * higher is better. Zero means "no match — exclude from results".
 *
 * Scoring:
 *   100 — exact match on a numeric secondary (e.g. CVM code).
 *    90 — exact match on label or shortcut keyword (case-insensitive).
 *    80 — label starts with query.
 *    70 — secondary starts with query.
 *    50 — label contains query as substring.
 *    40 — secondary contains query.
 *    30 — any keyword contains query.
 *     0 — no match.
 *
 * Group nudges (small) keep groups tied:
 *   +3 for companies (analyst's most common target).
 *   +1 for navigation.
 */
export function scoreCommand(cmd: Command, query: string): number {
  if (!query) return 0;
  const q = query.trim().toLowerCase();
  if (!q) return 0;

  const label = cmd.label.toLowerCase();
  const secondary = (cmd.secondary ?? "").toLowerCase();

  let score = 0;

  // Numeric CVM code exact match: super high signal.
  if (/^\d+$/.test(q) && cmd.group === "companies" && secondary.includes(`#${q}`)) {
    return 100;
  }

  if (label === q) score = Math.max(score, 90);
  if (secondary === q) score = Math.max(score, 90);
  if (label.startsWith(q)) score = Math.max(score, 80);
  if (secondary.startsWith(q)) score = Math.max(score, 70);
  if (label.includes(q)) score = Math.max(score, 50);
  if (secondary.includes(q)) score = Math.max(score, 40);
  for (const kw of cmd.keywords ?? []) {
    if (kw.toLowerCase().includes(q)) {
      score = Math.max(score, 30);
      break;
    }
  }

  if (score === 0) return 0;

  if (cmd.group === "companies") score += 3;
  else if (cmd.group === "navigation") score += 1;

  return score;
}

/**
 * Rank commands by score for the given query. Returns top `limit` entries,
 * sorted descending. Stable order: ties retain input order.
 */
export function rankCommands(
  commands: Command[],
  query: string,
  limit = 12,
): Command[] {
  if (!query.trim()) {
    // Empty query: surface navigation + actions only (companies require typing).
    return commands
      .filter((c) => c.group !== "companies")
      .slice(0, limit);
  }
  const scored: Array<{ cmd: Command; score: number; idx: number }> = [];
  commands.forEach((cmd, idx) => {
    const s = scoreCommand(cmd, query);
    if (s > 0) scored.push({ cmd, score: s, idx });
  });
  scored.sort((a, b) => (b.score - a.score) || (a.idx - b.idx));
  return scored.slice(0, limit).map((x) => x.cmd);
}
