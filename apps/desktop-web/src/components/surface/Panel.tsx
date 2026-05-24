import type { CSSProperties, ReactNode } from "react";

type HeadingLevel = 2 | 3 | 4;

type PanelProps = {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  dense?: boolean;
  className?: string;
  style?: CSSProperties;
  headingLevel?: HeadingLevel;
  "aria-label"?: string;
};

function renderHeading(level: HeadingLevel, children: ReactNode) {
  const style: CSSProperties = {
    color: "var(--color-text-primary)",
    fontSize: level === 2 ? "var(--text-lg)" : "var(--text-md)",
    fontWeight: 600,
    lineHeight: 1.25,
    margin: 0,
  };
  if (level === 2) return <h2 style={style}>{children}</h2>;
  if (level === 3) return <h3 style={style}>{children}</h3>;
  return <h4 style={style}>{children}</h4>;
}

export function Panel({
  title,
  subtitle,
  actions,
  children,
  footer,
  dense = false,
  className,
  style,
  headingLevel = 2,
  "aria-label": ariaLabel,
}: PanelProps) {
  const hasHeader = title || subtitle || actions;
  return (
    <article
      className={className}
      aria-label={!title ? ariaLabel : undefined}
      style={{
        background: "var(--color-surface-2)",
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "var(--radius-md)",
        overflow: "hidden",
        ...style,
      }}
    >
      {hasHeader ? (
        <header
          className="flex flex-wrap items-start justify-between gap-3"
          style={{
            borderBottom: "1px solid var(--color-border-subtle)",
            padding: dense ? "10px 12px" : "12px 16px",
          }}
        >
          <div className="min-w-0">
            {title ? renderHeading(headingLevel, title) : null}
            {subtitle ? (
              <p
                style={{
                  color: "var(--color-text-tertiary)",
                  fontSize: "var(--text-xs)",
                  margin: title ? "2px 0 0" : 0,
                }}
              >
                {subtitle}
              </p>
            ) : null}
          </div>
          {actions ? <div className="shrink-0">{actions}</div> : null}
        </header>
      ) : null}
      <div style={{ padding: dense ? "12px" : "16px" }}>{children}</div>
      {footer ? (
        <footer
          style={{
            borderTop: "1px solid var(--color-border-subtle)",
            color: "var(--color-text-tertiary)",
            fontSize: "var(--text-xs)",
            padding: dense ? "8px 12px" : "10px 16px",
          }}
        >
          {footer}
        </footer>
      ) : null}
    </article>
  );
}
