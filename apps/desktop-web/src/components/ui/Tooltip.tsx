import { useState } from "react";
import type { ReactNode } from "react";

/**
 * Minimal CSS-only tooltip. Renders next to the trigger on hover/focus.
 * No portal — caller must ensure the trigger's parent isn't `overflow:
 * hidden` if positioning matters. Good enough for terminal-grade hints.
 *
 * For more capable positioning (collision detection, virtual references),
 * a future revision can wrap floating-ui — out of scope for UX-3.
 */

type Props = {
  /** Tooltip body. */
  label: ReactNode;
  /** Trigger element. */
  children: ReactNode;
  /** Side of the trigger. Defaults to `top`. */
  side?: "top" | "bottom" | "right" | "left";
};

export function Tooltip({ label, children, side = "top" }: Props) {
  const [show, setShow] = useState(false);

  const offset = 6;
  const tipStyle: React.CSSProperties = {
    position: "absolute",
    background: "var(--color-surface-3)",
    color: "var(--color-text-primary)",
    border: "1px solid var(--color-border-strong)",
    borderRadius: "var(--radius-sm)",
    padding: "4px 8px",
    fontSize: "var(--text-xs)",
    whiteSpace: "nowrap",
    pointerEvents: "none",
    zIndex: "var(--z-overlay)" as unknown as number,
    opacity: show ? 1 : 0,
    transition: "opacity 120ms ease-out",
  };

  if (side === "top") {
    tipStyle.bottom = `calc(100% + ${offset}px)`;
    tipStyle.left = "50%";
    tipStyle.transform = "translateX(-50%)";
  } else if (side === "bottom") {
    tipStyle.top = `calc(100% + ${offset}px)`;
    tipStyle.left = "50%";
    tipStyle.transform = "translateX(-50%)";
  } else if (side === "right") {
    tipStyle.left = `calc(100% + ${offset}px)`;
    tipStyle.top = "50%";
    tipStyle.transform = "translateY(-50%)";
  } else {
    tipStyle.right = `calc(100% + ${offset}px)`;
    tipStyle.top = "50%";
    tipStyle.transform = "translateY(-50%)";
  }

  return (
    <span
      style={{ position: "relative", display: "inline-flex" }}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}
    >
      {children}
      <span role="tooltip" style={tipStyle}>
        {label}
      </span>
    </span>
  );
}
