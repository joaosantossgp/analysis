"use client";

import { useCallback, useEffect, useState, type KeyboardEvent } from "react";

type UseComboboxNavigationOptions<T> = {
  items: readonly T[];
  onSelect: (item: T) => void;
  onSubmit?: () => void;
  onEscape?: () => void;
};

type UseComboboxNavigationResult = {
  activeIndex: number;
  setActiveIndex: (index: number) => void;
  handleKeyDown: (event: KeyboardEvent<HTMLInputElement>) => void;
};

export function useComboboxNavigation<T>({
  items,
  onSelect,
  onSubmit,
  onEscape,
}: UseComboboxNavigationOptions<T>): UseComboboxNavigationResult {
  const [activeIndex, setActiveIndex] = useState(-1);

  useEffect(() => {
    setActiveIndex(items.length > 0 ? 0 : -1);
  }, [items]);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLInputElement>) => {
      if (event.key === "ArrowDown") {
        if (items.length === 0) return;
        event.preventDefault();
        setActiveIndex((current) =>
          current < items.length - 1 ? current + 1 : 0,
        );
        return;
      }

      if (event.key === "ArrowUp") {
        if (items.length === 0) return;
        event.preventDefault();
        setActiveIndex((current) =>
          current > 0 ? current - 1 : items.length - 1,
        );
        return;
      }

      if (event.key === "Escape") {
        setActiveIndex(-1);
        onEscape?.();
        return;
      }

      if (event.key === "Enter") {
        const active = activeIndex >= 0 ? items[activeIndex] : undefined;
        if (active) {
          event.preventDefault();
          onSelect(active);
          return;
        }
        onSubmit?.();
      }
    },
    [items, activeIndex, onSelect, onSubmit, onEscape],
  );

  return { activeIndex, setActiveIndex, handleKeyDown };
}
