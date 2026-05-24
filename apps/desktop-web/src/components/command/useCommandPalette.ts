import { useCallback, useEffect, useRef, useState } from "react";

import { useGlobalHotkeys } from "@/lib/keyboard/useGlobalHotkeys";

/**
 * Palette open/close state machine + global hotkey registration.
 *
 * Returns the current `open` flag plus stable `open`/`close`/`toggle`
 * callbacks. Tracks whether the palette has ever been opened — companies
 * index loader uses this signal so it doesn't pay the bridge cost until
 * the user actually invokes the palette.
 */

type PaletteState = {
  open: boolean;
  /** True once the palette has been opened at least once in this session. */
  primed: boolean;
  open_: () => void;
  close_: () => void;
  toggle_: () => void;
};

export function useCommandPalette(): PaletteState {
  const [open, setOpen] = useState(false);
  const primedRef = useRef(false);
  const [primed, setPrimed] = useState(false);

  const open_ = useCallback(() => {
    if (!primedRef.current) {
      primedRef.current = true;
      setPrimed(true);
    }
    setOpen(true);
  }, []);

  const close_ = useCallback(() => {
    setOpen(false);
  }, []);

  const toggle_ = useCallback(() => {
    if (!primedRef.current) {
      primedRef.current = true;
      setPrimed(true);
    }
    setOpen((prev) => !prev);
  }, []);

  // Ctrl+K / Cmd+K toggles. Esc closes.
  useGlobalHotkeys(
    ["ctrl+k", "meta+k"],
    (event) => {
      event.preventDefault();
      toggle_();
    },
    { enabledInInputs: true },
  );

  useGlobalHotkeys(
    "escape",
    () => {
      if (open) close_();
    },
    { enabledInInputs: true },
  );

  // Body scroll lock while open.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  return { open, primed, open_, close_, toggle_ };
}
