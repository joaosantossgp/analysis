import { Link } from "react-router-dom";
import { StateBanner } from "@/components/feedback/StateBanner";

export function RetiredNewsPage() {
  return <section className="space-y-4 p-6">
    <StateBanner variant="empty" title="News has been retired" message="News is no longer part of this workspace. Downloaded data and saved settings have been preserved." />
    <div className="flex gap-4"><Link to="/" className="text-id-link underline">Home</Link><Link to="/empresas" className="text-id-link underline">Open Companies</Link></div>
  </section>;
}
