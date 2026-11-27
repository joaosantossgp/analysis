import { Link } from "react-router-dom";

import { SectionFrame } from "../SectionFrame";
import type { DevPanelSection, DevPanelSectionProps } from "../sections";

export const DATA_OPS_PATH = "/dev/data-ops";

function ToolsSection({ closePanel }: DevPanelSectionProps) {
  return (
    <SectionFrame title="Tools">
      <Link
        to={DATA_OPS_PATH}
        className="text-sm"
        style={{ color: "var(--color-id-link)" }}
        onClick={() => {
          // The page stays hidden without this flag; opening it from the dev panel is the opt-in.
          window.localStorage?.setItem("cvm_dev_tools", "1");
          closePanel();
        }}
      >
        Data ops page →
      </Link>
      <p className="text-xs" style={{ color: "var(--color-text-tertiary)", margin: 0 }}>
        Reset the company universe or refresh jobs, simulate refresh outcomes, inspect raw state.
      </p>
    </SectionFrame>
  );
}

export const section: DevPanelSection = { id: "tools", order: 900, Component: ToolsSection };
