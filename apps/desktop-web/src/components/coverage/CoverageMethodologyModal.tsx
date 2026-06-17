import { useState, useEffect } from "react";
import { Button } from "@/components/ui/Button";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  defaultTab?: "scoring" | "capacity";
  availableHours?: number;
};

type TabId = "scoring" | "capacity";

export function CoverageMethodologyModal({ isOpen, onClose, defaultTab = "scoring", availableHours = 1600 }: Props) {
  const [activeTab, setActiveTab] = useState<TabId>(defaultTab);
  
  // Interactive simulator hours
  const [simHours, setSimHours] = useState<number>(availableHours);

  // Sync state when modal opens
  useEffect(() => {
    if (isOpen) {
      setActiveTab(defaultTab);
      setSimHours(availableHours);
    }
  }, [isOpen, defaultTab, availableHours]);

  if (!isOpen) return null;

  // Recalculations for interactive guide
  const weeksPerYear = 40;
  const daysPerWeek = 5;
  const weeklyHours = Math.round((simHours / weeksPerYear) * 10) / 10;
  const dailyHours = Math.round((weeklyHours / daysPerWeek) * 10) / 10;
  const fteCount = Math.round((simHours / 1600) * 100) / 100;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 font-mono text-xs select-none">
      <div
        className="w-full max-w-3xl bg-[var(--color-surface-1)] border border-[var(--color-border-default)] rounded shadow-2xl flex flex-col"
        style={{ height: "min(85vh, 650px)" }}
      >
        {/* Header */}
        <header className="p-4 border-b border-[var(--color-border-subtle)] flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-[var(--color-id-ticker)] uppercase tracking-wider">
              Coverage Methodology & Capacity Guide
            </h3>
            <p className="text-3xs text-[var(--color-text-tertiary)] mt-0.5">
              Reference guide for priority scores, complexity multipliers, and analyst workload allocation.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-200 focus:outline-none text-base font-sans"
          >
            &times;
          </button>
        </header>

        {/* Navigation Tabs */}
        <div className="flex border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-2)]">
          <button
            type="button"
            onClick={() => setActiveTab("scoring")}
            className={`px-4 py-2.5 border-r border-[var(--color-border-subtle)] font-bold tracking-wider ${
              activeTab === "scoring"
                ? "bg-[var(--color-surface-1)] text-cyan-400 border-b-2 border-b-cyan-500"
                : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-3)]"
            }`}
          >
            1. PRIORITY SCORING
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("capacity")}
            className={`px-4 py-2.5 border-r border-[var(--color-border-subtle)] font-bold tracking-wider ${
              activeTab === "capacity"
                ? "bg-[var(--color-surface-1)] text-cyan-400 border-b-2 border-b-cyan-500"
                : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-3)]"
            }`}
          >
            2. CAPACITY & WORKLOAD
          </button>
        </div>

        {/* Tab Contents */}
        <div className="flex-1 overflow-y-auto p-5 min-h-0 space-y-4">
          {activeTab === "scoring" ? (
            <div className="space-y-4 text-zinc-300 text-2xs leading-relaxed">
              <section className="space-y-1.5">
                <h4 className="text-xs font-bold text-zinc-100 uppercase tracking-wide border-b border-zinc-800 pb-1">
                  How Priority Score is Calculated
                </h4>
                <p>
                  The prioritization model ranks companies in your workspace based on a weighted average of four factors. Each factor ranges from <strong>0.0</strong> to <strong>100.0</strong>, and they are combined using your custom weights in the Settings panel:
                </p>
                <div className="bg-zinc-950/40 border border-zinc-900 rounded p-3 text-center text-zinc-200 text-xs font-bold my-2 select-text font-mono">
                  Score = (CapScore × w_cap) + (VolScore × w_vol) + (HoldScore × w_hold) + (SectScore × w_sect)
                </div>
              </section>

              <section className="space-y-2">
                <h4 className="text-xs font-bold text-zinc-100 uppercase tracking-wide border-b border-zinc-800 pb-1">
                  The Four Scoring Inputs
                </h4>
                <div className="space-y-3">
                  <div>
                    <span className="block text-cyan-400 font-bold uppercase tracking-wider">1. Market Cap Score (CapScore)</span>
                    <p className="mt-0.5">
                      Logarithmic scaling mapping company market capitalization from **R$ 10 Million** (0.0 points) to **R$ 50 Billion** (100.0 points). Logarithmic scaling prevents mega-cap outliers (like Vale or Petrobras) from completely dominating the ranking while keeping small caps relevant.
                    </p>
                  </div>
                  <div>
                    <span className="block text-cyan-400 font-bold uppercase tracking-wider">2. Liquidity / Trading Volume Score (VolScore)</span>
                    <p className="mt-0.5">
                      Logarithmic scaling mapping average 30-day trading volume from **R$ 10 Thousand** (0.0 points) to **R$ 100 Million** (100.0 points). Ensures liquidity is factored into analyst research priority.
                    </p>
                  </div>
                  <div>
                    <span className="block text-cyan-400 font-bold uppercase tracking-wider">3. Portfolio Holding % (HoldScore)</span>
                    <p className="mt-0.5">
                      Direct percentage representing the fund's current asset holdings (e.g., if the fund holds 15% of the company's capital, the score is 15.0; capped at 100.0). High holdings warrant high priority to monitor downside risks.
                    </p>
                  </div>
                  <div>
                    <span className="block text-cyan-400 font-bold uppercase tracking-wider">4. Sector Complexity Score (SectScore)</span>
                    <p className="mt-0.5">
                      Assigned based on research difficulty. Returns **100.0 points** for heavily regulated or complex sectors (Utilities, Electric Energy, Financial Intermediaries, and Oil & Gas), and **50.0 points** for all other sectors.
                    </p>
                  </div>
                </div>
              </section>

              <section className="space-y-1.5 pt-2 border-t border-zinc-800">
                <h4 className="text-xs font-bold text-zinc-100 uppercase tracking-wide">
                  Manual Override
                </h4>
                <p>
                  Analysts can apply a manual override (+/- score points) directly in the prioritization section. The manual override is added straight to the calculated score, clamping the final priority score between **0.0** and **100.0**. Any manual adjustment requires an audit trail rationale.
                </p>
              </section>
            </div>
          ) : (
            <div className="space-y-4 text-zinc-300 text-2xs leading-relaxed">
              <section className="space-y-1.5">
                <h4 className="text-xs font-bold text-zinc-100 uppercase tracking-wide border-b border-zinc-800 pb-1">
                  Capacity Boundary & Workload Model
                </h4>
                <p>
                  The Capacity Boundary measures the analyst team's annual available coverage bandwidth against the cumulative research hours required by all active companies in the workspace.
                </p>
              </section>

              <section className="space-y-2">
                <h4 className="text-xs font-bold text-zinc-100 uppercase tracking-wide border-b border-zinc-800 pb-1">
                  Base Tier Hours & Multipliers
                </h4>
                <p>
                  Each stock has a baseline amount of required hours per year, determined by its assigned Tier (e.g. *Must Cover* has a high baseline; *Watchlist* has a lower baseline). However, two compounding multipliers are applied to derive the actual research demand:
                </p>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 my-2">
                  <div className="bg-zinc-950/30 border border-zinc-900 rounded p-2.5 space-y-1">
                    <span className="block font-bold text-amber-400 uppercase tracking-wider">1. Sector Complexity Multiplier (1.2x)</span>
                    <p className="text-3xs text-zinc-400">
                      Applied to companies in highly regulated sectors (e.g. Electric Energy, Utilities, Oil & Gas, Financials). Adds 20% to research hours to account for reviewing voluminous regulatory filings, energy dispatch data, or capital requirements.
                    </p>
                  </div>
                  <div className="bg-zinc-950/30 border border-zinc-900 rounded p-2.5 space-y-1">
                    <span className="block font-bold text-amber-400 uppercase tracking-wider">2. Tier Rigor Multiplier (1.1x)</span>
                    <p className="text-3xs text-zinc-400">
                      Applied to stocks in the high-rigor tiers (**Must Cover** and **Core Coverage**). Adds 10% to the research hours due to strict audit checklist requirements, meeting frequency, and formal coverage updates.
                    </p>
                  </div>
                </div>

                <p className="text-3xs text-zinc-400 bg-zinc-950/20 border border-zinc-900 px-2.5 py-1.5 rounded italic">
                  <strong>Compounding Example:</strong> A stock in the *Must Cover* tier (base 120 hrs/year) operating in the *Electric Energy* sector will require: <code className="text-zinc-100">120 hrs × 1.2 (Sector) × 1.1 (Tier) = 158.4 hrs/year</code>.
                </p>
              </section>

              {/* Interactive Hour Calculator */}
              <section className="space-y-2.5 pt-3 border-t border-zinc-800">
                <h4 className="text-xs font-bold text-zinc-100 uppercase tracking-wide text-cyan-400">
                  Interactive Workload Translator
                </h4>
                <p>
                  Enter an annual hours quota below to see how it translates to standard analyst hours, weekly schedules, and daily workloads:
                </p>

                <div className="bg-zinc-950/45 border border-zinc-900 rounded p-3 flex flex-wrap items-center justify-between gap-4 font-mono">
                  <div className="space-y-1">
                    <label className="block text-3xs text-zinc-400 uppercase tracking-wider">Annual Hours</label>
                    <input
                      type="number"
                      value={simHours}
                      onChange={(e) => setSimHours(Math.max(0, Number(e.target.value)))}
                      className="bg-zinc-900 border border-zinc-800 rounded px-2.5 py-1 w-32 focus:outline-none text-zinc-200 text-xs font-bold text-right"
                    />
                  </div>

                  <div className="flex gap-6 text-center">
                    <div className="space-y-0.5">
                      <span className="block text-3xs text-zinc-500 uppercase tracking-wider">FTE Analysts</span>
                      <span className="block text-xs font-bold text-zinc-200">{fteCount} FTE</span>
                    </div>
                    <div className="space-y-0.5">
                      <span className="block text-3xs text-zinc-500 uppercase tracking-wider">Hours / Week</span>
                      <span className="block text-xs font-bold text-zinc-200">{weeklyHours} hrs/wk</span>
                    </div>
                    <div className="space-y-0.5">
                      <span className="block text-3xs text-zinc-500 uppercase tracking-wider">Hours / Day</span>
                      <span className="block text-xs font-bold text-zinc-200">{dailyHours} hrs/day</span>
                    </div>
                  </div>
                </div>

                <div className="text-3xs text-zinc-400 space-y-1 select-text bg-zinc-950/20 p-2.5 rounded border border-zinc-900">
                  <span className="block font-bold text-zinc-300 uppercase tracking-wider mb-1">Methodology Standards:</span>
                  <div>• **1 Full-Time Equivalent (FTE) Analyst** is modeled as **1600 hours/year** allocated purely to coverage.</div>
                  <div>• **Active Weeks/Year**: **40 weeks** (excludes vacations, corporate admin tasks, and general overhead).</div>
                  <div>• **Days/Week**: **5 days** (Monday to Friday, standard market trading hours).</div>
                  <div>• **Capacity Bounds Guideline**: Keeping utilization in the **80% to 95%** range is ideal. It keeps analysts engaged without inducing burnout, leaving a critical buffer for unexpected corporate events or earnings season spikes.</div>
                </div>
              </section>
            </div>
          )}
        </div>

        {/* Footer */}
        <footer className="p-4 border-t border-[var(--color-border-subtle)] flex justify-end bg-[var(--color-surface-2)]">
          <Button type="button" variant="primary" onClick={onClose}>
            Close Reference
          </Button>
        </footer>
      </div>
    </div>
  );
}
