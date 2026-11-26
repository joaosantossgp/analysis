import { useState, type CSSProperties, type ReactNode } from "react";

import { StateBanner } from "@/components/feedback/StateBanner";
import { Panel } from "@/components/surface/Panel";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Checkbox";
import { PeriodSelect } from "@/components/ui/PeriodSelect";

const NAV_ITEMS = [
  ["principles", "Principles"],
  ["foundations", "Foundations"],
  ["components", "Assets & Components"],
  ["motion", "Motion"],
  ["composition", "Composition"],
] as const;

const TOKENS = [
  ["Canvas", "--color-surface-1"],
  ["Panel", "--color-surface-2"],
  ["Raised", "--color-surface-3"],
  ["Border", "--color-border-default"],
  ["Text", "--color-text-primary"],
  ["Action", "--color-action-primary"],
] as const;

const CHART_COLORS = [
  "--color-chart-1",
  "--color-chart-2",
  "--color-chart-3",
  "--color-chart-4",
  "--color-chart-5",
  "--color-chart-6",
] as const;

export function DevDesignSystemPage() {
  const [motionPreviewOpen, setMotionPreviewOpen] = useState(false);

  return (
    <main className="design-reference-page">
      <header className="design-reference-header">
        <div>
          <p className="design-reference-eyebrow">Development only</p>
          <h1>Design Reference</h1>
          <p>
            The approved vocabulary for a dense, minimal, and dependable analytical workspace.
          </p>
          <p className="design-reference-shortcut">Ctrl + Alt + D</p>
          {/* PROTOTYPE (throwaway): entry to the data shell variants. */}
          <p>
            Prototype: <a href="#/?prototype=data-shell&variant=E&state=empty">Data shell — 5 variants</a>{" "}
            (← → variant, ↑ ↓ simulated state)
          </p>
        </div>
        <nav aria-label="Design reference sections" className="design-reference-nav">
          {NAV_ITEMS.map(([id, label]) => (
            <a key={id} href={`#${id}`}>{label}</a>
          ))}
        </nav>
      </header>

      <ReferenceSection id="principles" title="Principles" description="Rules that keep analytical work visible and the interface calm.">
        <div className="design-reference-rule-grid">
          <Rule title="Data before decoration" text="Prefer period, source, unit, and decision-relevant values over explanatory chrome." />
          <Rule title="One hierarchy" text="Use position, type scale, and neutral surfaces before adding labels, cards, or color." />
          <Rule title="Deliberate alignment" text="Equivalent headers, dividers, controls, and card heights must share a grid." />
          <Rule title="Detail on demand" text="Keep primary analysis visible; place secondary controls in compact popovers or disclosures." />
        </div>
      </ReferenceSection>

      <ReferenceSection id="foundations" title="Foundations" description="Use named tokens. Do not introduce ad-hoc colors, spacing, or rounded shapes.">
        <div className="design-reference-foundations">
          <div className="design-reference-token-grid">
            {TOKENS.map(([label, token]) => (
              <div key={token} className="design-reference-token">
                <span aria-hidden="true" style={{ background: `var(${token})` }} />
                <div><strong>{label}</strong><code>{token}</code></div>
              </div>
            ))}
          </div>
          <div className="design-reference-foundation-notes">
            <dl>
              <dt>Typeface</dt><dd>Inter for UI; JetBrains Mono for identifiers, periods, and numbers.</dd>
              <dt>Spacing</dt><dd>4 px base. Use 4, 8, 12, 16, 20, 24, 32, and 40 px.</dd>
              <dt>Radii</dt><dd>2–6 px only. No pills, soft cards, or ornamental shadows.</dd>
              <dt>Elevation</dt><dd>Reserved for overlays and drawers; structural surfaces use tonal contrast and borders.</dd>
            </dl>
            <div aria-label="Chart color palette" className="design-reference-chart-palette">
              {CHART_COLORS.map((token) => <span key={token} title={token} style={{ background: `var(${token})` }} />)}
            </div>
          </div>
        </div>
      </ReferenceSection>

      <ReferenceSection id="components" title="Assets & Components" description="Use existing controls before creating a new visual language.">
        <div className="design-reference-component-grid">
          <Specimen title="Actions" note="Orange communicates a primary action; secondary actions stay neutral.">
            <div className="flex flex-wrap gap-2"><Button variant="primary">Update data</Button><Button>Statements</Button><Button variant="ghost">More</Button></div>
          </Specimen>
          <Specimen title="Inputs" note="Labels provide context; compact controls carry the interaction.">
            <div className="flex flex-wrap items-center gap-3"><PeriodSelect ariaLabel="Reference period" value="5y" options={[{ value: "5y", label: "Last 5 years" }]} onChange={() => undefined} /><Checkbox label="Markers" checked onChange={() => undefined} /></div>
          </Specimen>
          <Specimen title="State" note="State always combines text, glyph, and color.">
            <StateBanner size="dense" variant="warning" title="Stale data" message="Local data remains available." />
          </Specimen>
          <Specimen title="Icons" note="Use a light, familiar outline; pair it with text for an action.">
            <div className="design-reference-icons"><OutlineIcon type="search" /><OutlineIcon type="download" /><OutlineIcon type="open" /><OutlineIcon type="line" /></div>
          </Specimen>
        </div>
      </ReferenceSection>

      <ReferenceSection id="motion" title="Motion" description="Motion explains a change of state. It never decorates the interface.">
        <div className="design-reference-motion-grid">
          <div>
            <ul className="design-reference-list">
              <li>Use opacity and a 4 px vertical transform for popovers and notices.</li>
              <li>Use 180 ms ease for entry and exit; progress may transition its width.</li>
              <li>Do not animate layout, run loops, or delay analytical content.</li>
              <li>Reduced-motion preferences remove non-essential transitions.</li>
            </ul>
            <Button size="sm" onClick={() => setMotionPreviewOpen((open) => !open)}>{motionPreviewOpen ? "Hide preview" : "Preview motion"}</Button>
          </div>
          <div className="design-reference-motion-stage">
            <div className={`design-reference-motion-popover${motionPreviewOpen ? " is-open" : ""}`} aria-hidden={!motionPreviewOpen}>
              <strong>Range updated</strong>
              <span>Local data is ready for analysis.</span>
            </div>
            <div className="design-reference-progress"><span style={{ width: motionPreviewOpen ? "72%" : "28%" }} /></div>
          </div>
        </div>
      </ReferenceSection>

      <ReferenceSection id="composition" title="Composition" description="Build screens from explicit relationships, not nested decoration.">
        <div className="design-reference-composition-grid">
          <Panel title="Company identity" subtitle="Entity context remains visible" dense>
            <div className="design-reference-identity"><strong>PETROBRAS PN</strong><span className="font-mono">B3&nbsp; PETR4</span><span>Energy · Integrated Oil &amp; Gas</span></div>
          </Panel>
          <Panel title="Financial Indicators" actions={<span className="font-mono text-[var(--color-text-tertiary)]">3/3 plotted</span>} dense>
            <div className="design-reference-mini-chart" aria-label="Example financial indicator chart"><span /><span /><span /><span /></div>
          </Panel>
        </div>
        <div className="design-reference-do-dont">
          <Rule title="Use" text="A single, aligned header; concise labels; source and status placed where they are needed." />
          <Rule title="Avoid" text="Nested cards, repeated helper copy, unequal adjacent components, decorative motion, and unbounded color." />
        </div>
      </ReferenceSection>
    </main>
  );
}

function ReferenceSection({ id, title, description, children }: { id: string; title: string; description: string; children: ReactNode }) {
  return <section id={id} className="design-reference-section"><div className="design-reference-section-heading"><h2>{title}</h2><p>{description}</p></div>{children}</section>;
}

function Rule({ title, text }: { title: string; text: string }) {
  return <article className="design-reference-rule"><h3>{title}</h3><p>{text}</p></article>;
}

function Specimen({ title, note, children }: { title: string; note: string; children: ReactNode }) {
  return <article className="design-reference-specimen"><div><h3>{title}</h3><p>{note}</p></div><div className="design-reference-specimen-content">{children}</div></article>;
}

function OutlineIcon({ type }: { type: "search" | "download" | "open" | "line" }) {
  const base: CSSProperties = { height: 22, stroke: "currentColor", strokeWidth: 1.8, width: 22 };
  if (type === "search") return <svg viewBox="0 0 24 24" aria-label="Search icon" style={base}><circle cx="11" cy="11" r="5.5" fill="none" /><path d="m16 16 4 4" /></svg>;
  if (type === "download") return <svg viewBox="0 0 24 24" aria-label="Download icon" style={base}><path d="M12 3v11m0 0 4-4m-4 4-4-4M4 19h16" fill="none" /></svg>;
  if (type === "open") return <svg viewBox="0 0 24 24" aria-label="Open in window icon" style={base}><path d="M14 4h6v6M20 4l-9 9M19 14v5H5V5h5" fill="none" /></svg>;
  return <svg viewBox="0 0 24 24" aria-label="Line chart icon" style={base}><path d="m3 17 6-6 4 3 8-8" fill="none" /><circle cx="3" cy="17" r="1" fill="currentColor" stroke="none" /><circle cx="9" cy="11" r="1" fill="currentColor" stroke="none" /><circle cx="13" cy="14" r="1" fill="currentColor" stroke="none" /><circle cx="21" cy="6" r="1" fill="currentColor" stroke="none" /></svg>;
}
