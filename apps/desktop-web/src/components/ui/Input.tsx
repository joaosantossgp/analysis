import { forwardRef } from "react";
import type { CSSProperties, InputHTMLAttributes } from "react";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  /** Apply monospace font + tabular nums. For tickers / CVM codes. */
  mono?: boolean;
  /** Full width by default; opt out via `block={false}`. */
  block?: boolean;
};

export const Input = forwardRef<HTMLInputElement, Props>(function Input(
  { mono = false, block = true, style, className, ...rest },
  ref,
) {
  const merged: CSSProperties = {
    width: block ? "100%" : undefined,
    background: "var(--color-surface-2)",
    color: "var(--color-text-primary)",
    border: "1px solid var(--color-border-default)",
    borderRadius: "var(--radius-md)",
    fontSize: "var(--text-base)",
    fontFamily: mono ? "var(--font-mono)" : "var(--font-sans)",
    fontVariantNumeric: mono ? "tabular-nums" : undefined,
    padding: "6px 10px",
    outline: "none",
    transition: "border-color 120ms ease-out",
    ...style,
  };
  return (
    <input
      ref={ref}
      className={className}
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
    />
  );
});
