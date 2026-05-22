import { Link } from "react-router-dom";

export interface BreadcrumbItem {
  label: string;
  to?: string;
}

export interface BreadcrumbsProps {
  items: BreadcrumbItem[];
}

export function Breadcrumbs({ items }: BreadcrumbsProps) {
  return (
    <nav aria-label="breadcrumb" className="text-xs text-zinc-500">
      <ol className="flex flex-wrap items-center">
        {items.map((item, idx) => {
          const isLast = idx === items.length - 1;
          return (
            <li key={idx} className="flex items-center">
              {idx > 0 && <span className="mx-2 text-zinc-700">/</span>}
              {item.to && !isLast ? (
                <Link to={item.to} className="hover:text-zinc-200 transition-colors">
                  {item.label}
                </Link>
              ) : (
                <span className="text-zinc-300 font-medium">{item.label}</span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
