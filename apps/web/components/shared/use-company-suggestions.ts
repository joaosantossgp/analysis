"use client";

import { useEffect, useRef, useState } from "react";

import {
  type CompanySuggestionItem,
  fetchCompanySuggestionsRoute,
  getUserFacingErrorMessage,
} from "@/lib/api";

type UseCompanySuggestionsOptions = {
  minLength?: number;
  debounceMs?: number;
  limit?: number;
};

type UseCompanySuggestionsResult = {
  suggestions: CompanySuggestionItem[];
  loading: boolean;
  error: string | null;
};

export function useCompanySuggestions(
  query: string,
  options: UseCompanySuggestionsOptions = {},
): UseCompanySuggestionsResult {
  const { minLength = 2, debounceMs = 250, limit = 6 } = options;

  const [suggestions, setSuggestions] = useState<CompanySuggestionItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cacheRef = useRef(new Map<string, CompanySuggestionItem[]>());

  useEffect(() => {
    const normalized = query.trim();
    if (normalized.length < minLength) {
      setSuggestions([]);
      setLoading(false);
      setError(null);
      return;
    }

    let active = true;
    setLoading(true);
    setError(null);

    const timer = window.setTimeout(async () => {
      try {
        const cached = cacheRef.current.get(normalized);
        if (cached) {
          if (active) setSuggestions(cached);
          return;
        }

        const payload = await fetchCompanySuggestionsRoute(normalized, limit);
        if (!active) return;

        const items = payload.items ?? [];
        cacheRef.current.set(normalized, items);
        setSuggestions(items);
      } catch (err) {
        if (!active) return;
        setSuggestions([]);
        setError(getUserFacingErrorMessage(err));
      } finally {
        if (active) setLoading(false);
      }
    }, debounceMs);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [query, minLength, debounceMs, limit]);

  return { suggestions, loading, error };
}
