import type { ReactNode } from "react";

/**
 * Minimal controlled tabs primitive. Underline indicator on active tab,
 * terminal palette. Consumer owns the active state and tab list.
 *
 * Usage:
 *   <Tabs>
 *     {tabs.map(t => (
 *       <Tabs.Item
 *         key={t.id}
 *         active={t.id === active}
 *         onClick={() => setActive(t.id)}
 *       >
 *         {t.label}
 *       </Tabs.Item>
 *     ))}
 *   </Tabs>
 */

type RootProps = {
  children: ReactNode;
  className?: string;
};

export function Tabs({ children, className }: RootProps) {
  return (
    <div
      role="tablist"
      className={className}
      style={{
        display: "flex",
        gap: 0,
        borderBottom: "1px solid var(--color-border-subtle)",
      }}
    >
      {children}
    </div>
  );
}

type ItemProps = {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
  disabled?: boolean;
};

function Item({ active, onClick, children, disabled }: ItemProps) {
  return (
    <button
      role="tab"
      aria-selected={active}
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        background: "transparent",
        border: "none",
        padding: "6px 12px",
        fontSize: "var(--text-sm)",
        fontFamily: "var(--font-sans)",
        color: active ? "var(--color-text-primary)" : "var(--color-text-tertiary)",
        borderBottom: active
          ? "2px solid var(--color-action-primary)"
          : "2px solid transparent",
        marginBottom: "-1px",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
        transition: "color 120ms ease-out",
      }}
    >
      {children}
    </button>
  );
}

Tabs.Item = Item;
