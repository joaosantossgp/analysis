import { forwardRef } from "react";
import type { CSSProperties, InputHTMLAttributes, ReactNode } from "react";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label?: ReactNode;
};

/**
 * 14x14 sharp-corner checkbox in the terminal palette. Native input
 * underneath for accessibility; visual is custom via accent-color.
 */
export const Checkbox = forwardRef<HTMLInputElement, Props>(function Checkbox(
  { label, style, ...rest },
  ref,
) {
  const inputStyle: CSSProperties = {
    width: 14,
    height: 14,
    accentColor: "var(--color-action-primary)",
    cursor: rest.disabled ? "not-allowed" : "pointer",
    margin: 0,
    ...style,
  };
  if (!label) {
    return <input ref={ref} type="checkbox" style={inputStyle} {...rest} />;
  }
  return (
    <label
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        cursor: rest.disabled ? "not-allowed" : "pointer",
        fontSize: "var(--text-sm)",
        color: "var(--color-text-primary)",
      }}
    >
      <input ref={ref} type="checkbox" style={inputStyle} {...rest} />
      <span>{label}</span>
    </label>
  );
});
