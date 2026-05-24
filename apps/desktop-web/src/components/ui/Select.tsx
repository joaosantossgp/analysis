import { forwardRef } from "react";
import type { CSSProperties, SelectHTMLAttributes } from "react";

type Props = SelectHTMLAttributes<HTMLSelectElement> & {
  block?: boolean;
};

/**
 * Native `<select>` re-styled to match the terminal palette. Keeps
 * accessibility + keyboard semantics free.
 */
export const Select = forwardRef<HTMLSelectElement, Props>(function Select(
  { block = true, style, children, ...rest },
  ref,
) {
  const merged: CSSProperties = {
    width: block ? "100%" : undefined,
    background: "var(--color-surface-2)",
    color: "var(--color-text-primary)",
    border: "1px solid var(--color-border-default)",
    borderRadius: "var(--radius-md)",
    fontSize: "var(--text-base)",
    fontFamily: "var(--font-sans)",
    padding: "6px 10px",
    outline: "none",
    transition: "border-color 120ms ease-out",
    cursor: rest.disabled ? "not-allowed" : "pointer",
    ...style,
  };
  return (
    <select
      ref={ref}
      style={merged}
      onFocus={(e) => {
        e.currentTarget.style.borderColor = "var(--color-action-primary)";
        rest.onFocus?.(e);
      }}
      onBlur={(e) => {
        e.currentTarget.style.borderColor = "var(--color-border-default)";
        rest.onBlur?.(e);
      }}
      {...rest}
    >
      {children}
    </select>
  );
});
