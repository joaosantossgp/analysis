"use client";

import { useCallback, useState, type KeyboardEvent } from "react";

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

type ActiveIndexState<T> = {
  items: readonly T[];
  activeIndex: number;
};

function getInitialActiveIndex(items: readonly unknown[]): number {
  return items.length > 0 ? 0 : -1;
}

function clampActiveIndex(index: number, items: readonly unknown[]): number {
  if (items.length === 0) {
    return -1;
  }
  if (index >= items.length) {
    return items.length - 1;
  }
  return index;
}

export function useComboboxNavigation<T>({
  items,
  onSelect,
  onSubmit,
  onEscape,
}: UseComboboxNavigationOptions<T>): UseComboboxNavigationResult {
  const [activeState, setActiveState] = useState<ActiveIndexState<T>>(() => ({
    items,
    activeIndex: getInitialActiveIndex(items),
  }));
  const activeIndex =
    activeState.items === items
      ? clampActiveIndex(activeState.activeIndex, items)
      : getInitialActiveIndex(items);
  const setActiveIndex = useCallback(
    (nextIndex: number) => {
      setActiveState({ items, activeIndex: nextIndex });
    },
    [items],
  );

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLInputElement>) => {
      if (event.key === "ArrowDown") {
        if (items.length === 0) return;
        event.preventDefault();
        setActiveState({
          items,
          activeIndex: activeIndex < items.length - 1 ? activeIndex + 1 : 0,
        });
        return;
      }

      if (event.key === "ArrowUp") {
        if (items.length === 0) return;
        event.preventDefault();
        setActiveState({
          items,
          activeIndex: activeIndex > 0 ? activeIndex - 1 : items.length - 1,
        });
        return;
      }

      if (event.key === "Escape") {
        setActiveState({ items, activeIndex: -1 });
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
