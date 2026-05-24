import { forwardRef } from "react";
import type { ButtonHTMLAttributes, CSSProperties } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "xs" | "sm" | "md";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  /** Make the button take full container width. */
  block?: boolean;
};

function styleFor(variant: Variant, disabled: boolean): CSSProperties {
  const base: CSSProperties = {
    borderRadius: "var(--radius-md)",
    border: "1px solid transparent",
    fontFamily: "var(--font-sans)",
    fontWeight: 500,
    cursor: disabled ? "not-allowed" : "pointer",
    transition: "background 120ms ease-out, border-color 120ms ease-out, color 120ms ease-out",
    opacity: disabled ? 0.5 : 1,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
  };
  switch (variant) {
    case "primary":
      return {
        ...base,
        background: "var(--color-action-primary)",
        color: "var(--color-text-inverse)",
        borderColor: "var(--color-action-primary)",
      };
    case "secondary":
      return {
        ...base,
        background: "transparent",
        color: "var(--color-text-primary)",
        borderColor: "var(--color-border-default)",
      };
    case "ghost":
      return {
        ...base,
        background: "transparent",
        color: "var(--color-text-secondary)",
        borderColor: "transparent",
      };
    case "danger":
      return {
        ...base,
        background: "var(--color-state-err)",
        color: "var(--color-text-inverse)",
        borderColor: "var(--color-state-err)",
      };
  }
}

function sizeFor(size: Size): CSSProperties {
  switch (size) {
    case "xs":
      return { fontSize: "var(--text-xs)", padding: "2px 8px", height: 22 };
    case "sm":
      return { fontSize: "var(--text-sm)", padding: "4px 12px", height: 28 };
    case "md":
      return { fontSize: "var(--text-base)", padding: "6px 16px", height: 32 };
  }
}

export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  {
    variant = "secondary",
    size = "sm",
    loading = false,
    block = false,
    disabled,
    style,
    children,
    ...rest
  },
  ref,
) {
  const merged: CSSProperties = {
    ...styleFor(variant, !!disabled || loading),
    ...sizeFor(size),
    width: block ? "100%" : undefined,
    ...style,
  };
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      style={merged}
      {...rest}
    >
      {loading ? (
        <span aria-hidden="true" className="font-mono" style={{ fontSize: "var(--text-xs)" }}>
          ●●●
        </span>
      ) : null}
      {children}
    </button>
  );
});
