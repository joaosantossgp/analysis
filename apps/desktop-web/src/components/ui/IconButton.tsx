import { forwardRef } from "react";
import type { ButtonHTMLAttributes, CSSProperties } from "react";

type Size = "xs" | "sm" | "md";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  size?: Size;
  /** Required: screen-reader-visible label for the icon-only control. */
  "aria-label": string;
};

function sizeFor(size: Size): { dim: number; font: string } {
  switch (size) {
    case "xs":
      return { dim: 20, font: "var(--text-xs)" };
    case "sm":
      return { dim: 24, font: "var(--text-sm)" };
    case "md":
      return { dim: 28, font: "var(--text-base)" };
  }
}

export const IconButton = forwardRef<HTMLButtonElement, Props>(function IconButton(
  { size = "sm", disabled, style, children, ...rest },
  ref,
) {
  const { dim, font } = sizeFor(size);
  const merged: CSSProperties = {
    width: dim,
    height: dim,
    background: "transparent",
    color: "var(--color-text-secondary)",
    border: "1px solid transparent",
    borderRadius: "var(--radius-sm)",
    cursor: disabled ? "not-allowed" : "pointer",
    fontSize: font,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    opacity: disabled ? 0.5 : 1,
    transition: "background 120ms ease-out, color 120ms ease-out",
    ...style,
  };
  return (
    <button ref={ref} disabled={disabled} style={merged} {...rest}>
      {children}
    </button>
  );
});
