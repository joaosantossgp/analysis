import { Link } from "react-router-dom";
import { Panel } from "@/components/surface/Panel";
import type { WidgetCommonProps } from "./shared/widgetTypes";

export function RetiredNewsCard({ headerControls, isMinimized, onRemove }: WidgetCommonProps) {
  return <Panel title="News has been retired" actions={headerControls}>
    {!isMinimized && <div className="space-y-3 text-sm text-secondary">
      <p>Your downloaded news and saved widget configuration have been preserved. This widget no longer loads news.</p>
      <Link to="/empresas" className="text-id-link underline">Open Companies</Link>
      <button type="button" onClick={onRemove} className="block underline">Remove from layout</button>
    </div>}
  </Panel>;
}
