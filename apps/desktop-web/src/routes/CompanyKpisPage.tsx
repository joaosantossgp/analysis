import { useParams } from "react-router-dom";
import { Navigate } from "react-router-dom";

/**
 * The company-specific Indicators tab has been merged into the Overview page.
 * This module exists solely to provide a backward-compatible redirect so that
 * existing bookmarks or deep links to /empresas/:cdCvm/indicadores are
 * transparently forwarded to the corresponding Overview page.
 *
 * Do NOT restore page content here. The indicator chart is now rendered
 * directly inside CompanyDetailPage (the Overview workspace).
 */
export function CompanyKpisPage() {
  const params = useParams<{ cdCvm: string }>();
  return <Navigate to={`/empresas/${params.cdCvm ?? ""}`} replace />;
}
