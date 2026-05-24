import { callBridge, getBridgeMode } from "../bridge/adapter";
import type {
  CompanyUniversePreset,
  OnboardingStartResponse,
  OnboardingState,
} from "../bridge/types";

const BROWSER_REASON =
  "Running in browser preview. First-run setup is available in the desktop app.";

export type OnboardingStateResult =
  | { mode: "desktop"; state: OnboardingState }
  | { mode: "browser"; state: OnboardingState; reason: string };

export const COMPANY_UNIVERSE_PRESETS: Array<{
  value: CompanyUniversePreset;
  title: string;
  label: string;
  description: string;
  recommended?: boolean;
}> = [
  {
    value: "top_100",
    title: "Top 100",
    label: "Fastest",
    description: "Fastest setup. Best for large caps and quick exploration.",
  },
  {
    value: "top_200",
    title: "Top 200",
    label: "Recommended",
    description: "Recommended. Balanced coverage for most analysis workflows.",
    recommended: true,
  },
  {
    value: "top_500",
    title: "Top 500",
    label: "Broad",
    description: "Broad coverage. Takes longer and uses more local storage.",
  },
  {
    value: "all",
    title: "All B3 companies",
    label: "Complete",
    description: "Complete dataset. Best for full-market research.",
  },
];

export async function fetchOnboardingState(): Promise<OnboardingStateResult> {
  if (getBridgeMode() === "browser") {
    return {
      mode: "browser",
      reason: BROWSER_REASON,
      state: {
        first_run_completed: true,
        should_show: false,
        selected_company_universe: null,
        company_universe_source: null,
        company_universe_source_date: null,
        setup_status: "browser_preview",
        selected_company_count: 0,
        refresh_job_id: null,
        warning: null,
        has_local_financial_data: false,
        market_cap_source_available: false,
      },
    };
  }
  const state = await callBridge("get_onboarding_state", {});
  if (state.error) {
    throw new Error(state.error);
  }
  return { mode: "desktop", state };
}

export async function startOnboardingSetup(
  preset: CompanyUniversePreset,
): Promise<OnboardingStartResponse> {
  if (getBridgeMode() === "browser") {
    throw new Error(BROWSER_REASON);
  }
  const response = await callBridge("start_onboarding_setup", { preset });
  if (response.error) {
    throw new Error(response.error);
  }
  if (response.status === "error") {
    throw new Error(
      response.message ||
        response.status_reason_message ||
        "Could not start company setup.",
    );
  }
  return response;
}

export async function completeOnboardingSetup(): Promise<OnboardingState> {
  if (getBridgeMode() === "browser") {
    throw new Error(BROWSER_REASON);
  }
  return callBridge("complete_onboarding_setup", { status: "success" });
}

export async function skipOnboardingSetup(): Promise<OnboardingState> {
  if (getBridgeMode() === "browser") {
    throw new Error(BROWSER_REASON);
  }
  return callBridge("skip_onboarding_setup", {});
}
