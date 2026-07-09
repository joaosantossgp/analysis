---
name: CVM Analytics
description: Local, auditable financial analysis for Brazilian public company data.
colors:
  background: "oklch(0.145 0 0)"
  foreground: "oklch(0.985 0 0)"
  card: "oklch(0.205 0 0)"
  muted: "oklch(0.269 0 0)"
  muted-foreground: "oklch(0.708 0 0)"
  border: "oklch(1 0 0 / 10%)"
  input: "oklch(1 0 0 / 15%)"
  primary: "oklch(0.72 0.14 178)"
  primary-foreground: "oklch(0.985 0 0)"
  destructive: "oklch(0.704 0.191 22.216)"
  chart-teal: "oklch(0.72 0.15 161.56)"
  chart-amber: "oklch(0.75 0.16 29)"
  chart-blue-violet: "oklch(0.7 0.13 258)"
  chart-lime: "oklch(0.78 0.12 79)"
  chart-rose: "oklch(0.73 0.14 320)"
typography:
  display:
    fontFamily: "Space Grotesk, Manrope, system-ui, sans-serif"
    fontSize: "2.5rem"
    fontWeight: 500
    lineHeight: 1.05
    letterSpacing: "0"
  headline:
    fontFamily: "Space Grotesk, Manrope, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 500
    lineHeight: 1.15
    letterSpacing: "0"
  title:
    fontFamily: "Space Grotesk, Manrope, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 500
    lineHeight: 1.25
    letterSpacing: "0"
  body:
    fontFamily: "Manrope, system-ui, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 400
    lineHeight: 1.65
    letterSpacing: "0"
  label:
    fontFamily: "Manrope, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.15em"
  mono:
    fontFamily: "IBM Plex Mono, ui-monospace, monospace"
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "0"
rounded:
  sm: "0.525rem"
  md: "0.7rem"
  lg: "0.875rem"
  xl: "1.225rem"
  surface: "1.75rem"
  full: "9999px"
spacing:
  xs: "0.25rem"
  sm: "0.5rem"
  md: "1rem"
  lg: "1.5rem"
  xl: "2rem"
  shell-x-mobile: "1rem"
  shell-x-tablet: "1.5rem"
  shell-x-desktop: "2.5rem"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-foreground}"
    rounded: "{rounded.lg}"
    padding: "0.25rem 0.625rem"
    height: "2rem"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.foreground}"
    rounded: "{rounded.full}"
    padding: "0.25rem 1rem"
    height: "1.75rem"
  input-default:
    backgroundColor: "{colors.input}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.lg}"
    padding: "0.25rem 0.625rem"
    height: "2rem"
  card-default:
    backgroundColor: "{colors.card}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.xl}"
    padding: "1rem"
  chip-default:
    backgroundColor: "{colors.muted}"
    textColor: "{colors.muted-foreground}"
    rounded: "{rounded.full}"
    padding: "0.375rem 0.75rem"
---

# Design System: CVM Analytics

## 1. Overview

**Creative North Star: "The Audit Desk"**

CVM Analytics should feel like a focused analyst workstation: dark, precise, local, and trustworthy. The interface serves comparison and verification, so hierarchy, period context, coverage, and state must be clearer than decoration.

The system is restrained by default. Neutral surfaces create the workspace; teal marks action, selection, focus, and high-value signals. Density is allowed because the user is comparing financial data, but every dense region needs clear grouping, legible labels, and enough spacing to avoid a generic dashboard blur.

This system explicitly rejects a dashboard SaaS generico look. It must not drift into promo-fintech polish, neon crypto language, raw spreadsheet UI, or chart spectacle that hides auditability.

**Key Characteristics:**
- Dark, restrained, and task-first.
- Dense but controlled financial information.
- Teal accent used for action and current state, never decoration.
- Rounded, bordered surfaces with tonal layering instead of heavy shadows.
- Visible evidence: periods, data states, filters, and empty/error states are part of the design.

### Product Minimalism

Minimalism is a core product principle for CVM Analytics. It does not mean
fewer tools or less data. It means the screen shows the right information with
strong hierarchy, consistent patterns, low friction, and no unnecessary visual
or textual noise.

Design decision: less is more useful when it means fewer visible decisions,
fewer repeated labels, fewer decorative containers, and fewer generic words. It
is not useful when it removes source, period, unit, method, caveat, state, or
the next action needed for an analyst to trust the screen.

For this product, a minimal screen should still be dense when density helps an
analyst compare companies, periods, sources, or indicators. Remove clutter, not
evidence. Source, period, unit, currency, consolidation type, calculation
method, missing data, and data-quality issues must remain available when they
affect interpretation.

### Minimalism Review Rules

- Start with the analyst task: selection, source data, indicator, historical
  trend, interpretation, export, or next action.
- Put summary first, then filters and primary data, then detail on demand.
- Prefer compact tables, clear section titles, stable filters, and direct
  actions over decorative cards or generic dashboard grids.
- Remove repeated labels, vague helper copy, duplicate controls, ornamental
  badges, and chart containers that do not improve interpretation.
- Treat redundant summary panels as a product error. A summary should add a new
  decision, action, source drill-down, or method explanation; otherwise it is
  noise even when it looks organized.
- Keep empty, loading, error, stale, and partial-data states explicit and close
  to the affected data.
- Do not hide audit fields to make the UI look cleaner.
- Use visual hierarchy to separate essential information, secondary context,
  and optional detail.
- If a screen feels busy, first reduce duplication and unclear hierarchy before
  removing analytical content.

## 2. Colors

The palette is a restrained dark-neutral system with one operational teal accent and a small chart vocabulary.

### Primary
- **Regulatory Teal** (`primary`): use for primary actions, current selection, focus rings, active chart markers, and rare positive emphasis. Its scarcity is part of the premium feel.

### Secondary
- **Statement Amber** (`chart-amber`): use in charts and warning-adjacent financial states where contrast against teal is required. Do not use it as a generic brand accent.

### Tertiary
- **Ledger Blue-Violet**, **Coverage Lime**, and **Audit Rose** (`chart-blue-violet`, `chart-lime`, `chart-rose`): reserved for multi-series charts and categorical comparison. They should appear with labels or legends, never as meaning by color alone.

### Neutral
- **Desk Black** (`background`): primary app canvas in dark mode.
- **Panel Charcoal** (`card`): cards, popovers, menus, and local panels.
- **Control Graphite** (`muted`, `input`): selected navigation, input fill, subdued regions, and table hover states.
- **High-Contrast Ink** (`foreground`): primary text and numeric values.
- **Muted Ledger Text** (`muted-foreground`): secondary labels, timestamps, metadata, and helper text.
- **Hairline Boundary** (`border`): component edges, dividers, gridlines, and table separators.

### Named Rules

**The One Accent Rule.** Teal is for action, selection, focus, and signal. If teal appears as background decoration, the screen is losing discipline.

**The Evidence Contrast Rule.** Text and chart elements required for understanding must meet practical WCAG AA contrast; muted text can be quiet, but it cannot become decorative noise.

## 3. Typography

**Display Font:** Space Grotesk, with Manrope and system fallbacks.
**Body Font:** Manrope, with system fallbacks.
**Label/Mono Font:** IBM Plex Mono for tabular or code-like numeric contexts.

**Character:** The pairing is technical without feeling like a terminal. Space Grotesk gives headings a compact market-analysis character; Manrope keeps dense UI labels readable; IBM Plex Mono supports tabular numbers and audit trails.

### Hierarchy
- **Display** (500, 2.5rem, 1.05): page-level titles and major empty/error states only.
- **Headline** (500, 1.75rem, 1.15): dashboard section titles, company headers, and major panels.
- **Title** (500, 1.25rem, 1.25): card titles, chart headings, and toolbars.
- **Body** (400, 0.95rem, 1.65): descriptions, table context, and explanatory text. Keep prose near 65-75 characters per line.
- **Label** (600, 0.75rem, 0.15em tracking, uppercase): eyebrows, table headers, compact filter labels, and metadata.
- **Mono** (500, 0.875rem, 1.4): numeric readouts that require alignment or audit clarity.

### Named Rules

**The Data First Rule.** Numbers, labels, and periods must be readable before headings become expressive. Do not use display-scale type inside compact cards or controls.

## 4. Elevation

Depth is mostly tonal: borders, background opacity, and subtle rings separate layers. Shadows are reserved for menus, sticky navigation, hover affordances, and high-level surfaces. The default state should feel stable, not floating.

### Shadow Vocabulary
- **Surface Drift** (`0 24px 70px -48px rgba(16,30,24,0.34)`): large section surfaces that need separation from the page.
- **Menu Lift** (`0 20px 50px -20px rgba(16,30,24,0.3)`): dropdown menus and overlays.
- **Mobile Sheet Lift** (`0 20px 40px -28px rgba(16,30,24,0.28)`): mobile navigation and temporary panels.
- **Control Hairline** (`ring-1 ring-foreground/10`): card-level boundaries where a full shadow would be too heavy.

### Named Rules

**The Flat At Rest Rule.** Surfaces are stable at rest. Add shadow only when the element is elevated by structure or interaction.

## 5. Components

### Buttons
- **Shape:** compact rounded rectangles for app controls (`0.875rem`) and full pills for navigation/filter chips (`9999px`).
- **Primary:** Regulatory Teal background with primary foreground text; compact height (`2rem`) by default.
- **Hover / Focus:** hover reduces or shifts background tone; focus uses a visible 3px ring with the ring token at 50% opacity.
- **Secondary / Ghost / Tertiary:** ghost buttons stay transparent until hover or active state; outline buttons use the same border/input vocabulary as fields.

### Chips
- **Style:** full-pill shape with border and subdued fill. Brand chips use a low-opacity teal background, not saturated teal blocks.
- **State:** selected chips move toward `muted` or `primary/10`; unselected chips remain low-contrast but readable.

### Cards / Containers
- **Corner Style:** component cards use `0.875rem` to `1.225rem`; large product surfaces use `1.75rem`.
- **Background:** cards use `card` or semi-transparent `background`; nested card-on-card treatment should be avoided.
- **Shadow Strategy:** use tonal layering first, shadow second.
- **Border:** use `border/60` to `border/70` for quiet structure.
- **Internal Padding:** compact cards start at `1rem`; dashboard surfaces use `1.5rem` to `2.5rem` depending on density.

### Inputs / Fields
- **Style:** 2rem height, rounded-lg, `border-input`, transparent or `input/30` background in dark mode.
- **Focus:** border changes to ring color and adds a 3px ring; focus must be visible on keyboard.
- **Error / Disabled:** destructive ring for invalid states; disabled controls lower opacity and remove interaction.

### Navigation
- **Style:** sticky top bar, 4rem height, blurred dark background, hairline bottom border.
- **Typography:** compact text labels with subtle opacity until hover/active.
- **Active State:** active route uses muted fill and foreground text. Dropdowns use card background, rounded corners, icon containers, and concise helper labels.
- **Mobile:** mobile menu becomes a stacked panel with the same muted, bordered vocabulary.

### Tables and Data Regions
- **Style:** tabular density is allowed. Header labels are small, uppercase, and muted; rows use thin dividers and quiet hover fill.
- **State:** loading uses skeletons in the real layout. Empty and error states must explain data availability or refresh action.

### Charts
- **Style:** chart lines use the chart tokens with subdued gridlines and clear legends.
- **State:** charts need readable empty, loading, and error states. A chart without selected indicators should explain the selection action instead of rendering fallback data silently.

## 6. Do's and Don'ts

### Do:
- **Do** keep the product dark, restrained, dense, and audit-focused.
- **Do** use `primary` teal for action, current state, focus, and meaningful signal.
- **Do** show period context, selected filters, data coverage, loading, empty, and error states close to the component they affect.
- **Do** use borders, muted fills, and subtle rings before adding shadow.
- **Do** keep chart legends, labels, and tooltips explicit enough that color is not the only source of meaning.
- **Do** preserve keyboard focus states on filters, dropdowns, calendar controls, tabs, and table actions.

### Don't:
- **Don't** make the interface look like a dashboard SaaS generico.
- **Don't** use neon crypto styling, purple-blue glow defaults, generic fintech landing polish, or raw spreadsheet presentation.
- **Don't** add duplicated filters, nested cards, or decorative chart containers that weaken hierarchy.
- **Don't** use teal as ornamental background texture.
- **Don't** rely on color alone for financial state, chart identity, or warning severity.
- **Don't** introduce side-stripe accent cards, gradient text, glassmorphism as default, or decorative motion.
