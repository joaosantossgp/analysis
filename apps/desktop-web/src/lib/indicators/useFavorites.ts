/**
 * Pinned/favorite indicators, persisted to localStorage.
 *
 * Favorites are a personal workflow preference (which indicators a user keeps
 * coming back to), so they persist under a single scoped key. Reads/writes are
 * try/catch wrapped and shape-validated — a corrupt or absent value degrades to
 * an empty set rather than throwing. Mirrors the persistence pattern in
 * `useIndicatorConfig.ts` / `useCountryKpiConfig.ts`.
 */
import { useCallback, useEffect, useRef, useState } from "react";

const STORAGE_KEY = "cvm:indicators:favorites:v1";

function load(): Set<string> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((x): x is string => typeof x === "string" && x.length > 0));
  } catch {
    return new Set();
  }
}

export interface UseFavorites {
  favorites: Set<string>;
  isFavorite: (id: string) => boolean;
  toggle: (id: string) => void;
  clear: () => void;
  count: number;
}

export function useFavorites(): UseFavorites {
  const [favorites, setFavorites] = useState<Set<string>>(load);

  // rAF-debounced persist so rapid toggles don't thrash localStorage.
  const frame = useRef<number | null>(null);
  useEffect(() => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify([...favorites]));
      } catch {
        /* storage unavailable / quota — keep in memory only */
      }
    });
    return () => {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
    };
  }, [favorites]);

  const toggle = useCallback((id: string) => {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const clear = useCallback(() => setFavorites(new Set()), []);

  const isFavorite = useCallback((id: string) => favorites.has(id), [favorites]);

  return { favorites, isFavorite, toggle, clear, count: favorites.size };
}
