import { useEffect } from "react";

/**
 * Global hotkey registration. Bind a key chord to a handler at the window
 * level. Single canonical site so every keyboard shortcut lives in one
 * place — discoverable, conflict-free.
 *
 * Chord syntax: lowercase letter optionally prefixed with modifiers in a
 * fixed order (`ctrl+`, `meta+`, `shift+`, `alt+`). Examples:
 *   "ctrl+k", "meta+k", "ctrl+/", "escape"
 *
 * For cross-platform Ctrl-or-Meta, register both: `["ctrl+k", "meta+k"]`.
 */

type Handler = (event: KeyboardEvent) => void;

type Options = {
  /** Whether the handler runs when focus is in an editable element. Default: false. */
  enabledInInputs?: boolean;
};

const EDITABLE_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

function isEditableTarget(target: EventTarget | null): boolean {
  if (!target) return false;
  if (!(target instanceof HTMLElement)) return false;
  if (EDITABLE_TAGS.has(target.tagName)) return true;
  if (target.isContentEditable) return true;
  return false;
}

function eventMatches(event: KeyboardEvent, chord: string): boolean {
  const parts = chord.toLowerCase().split("+");
  const key = parts[parts.length - 1];
  const modifiers = new Set(parts.slice(0, -1));

  if (modifiers.has("ctrl") !== event.ctrlKey) return false;
  if (modifiers.has("meta") !== event.metaKey) return false;
  if (modifiers.has("shift") !== event.shiftKey) return false;
  if (modifiers.has("alt") !== event.altKey) return false;

  return event.key.toLowerCase() === key;
}

export function useGlobalHotkeys(
  chords: string | string[],
  handler: Handler,
  options: Options = {},
): void {
  const chordList = Array.isArray(chords) ? chords : [chords];

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (!options.enabledInInputs && isEditableTarget(event.target)) {
        // Allow Escape and Ctrl+K to fire even inside inputs — they are
        // universal "exit / open palette" gestures.
        const isPalette = chordList.some(
          (c) => c.toLowerCase() === "ctrl+k" || c.toLowerCase() === "meta+k",
        );
        const isEscape = chordList.includes("escape");
        if (!isPalette && !isEscape) return;
      }
      for (const chord of chordList) {
        if (eventMatches(event, chord)) {
          handler(event);
          return;
        }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [chordList.join("|"), handler, options.enabledInInputs]); // eslint-disable-line react-hooks/exhaustive-deps
}
