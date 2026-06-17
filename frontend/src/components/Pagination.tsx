import { ChevronLeft, ChevronRight } from "lucide-react";

interface Props {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}

// Lists paginate at 25/page (page_size owned by caller). This control assumes
// 1-based pages and clamps within [1, totalPages].
export default function Pagination({
  page,
  totalPages,
  total,
  pageSize,
  onPageChange,
}: Props) {
  if (totalPages <= 1) return null;

  const safePage = Math.min(Math.max(page, 1), totalPages);
  const first = total === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const last = Math.min(safePage * pageSize, total);

  const go = (p: number) => {
    const clamped = Math.min(Math.max(p, 1), totalPages);
    if (clamped !== safePage) onPageChange(clamped);
  };

  const pages = pageWindow(safePage, totalPages);

  return (
    <nav
      className="mt-6 flex flex-col items-center justify-between gap-3 sm:flex-row"
      aria-label="Pagination"
    >
      <p className="num text-xs text-cold">
        {first}&ndash;{last} of {total.toLocaleString("en-US")}
      </p>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => go(safePage - 1)}
          disabled={safePage <= 1}
          aria-label="Previous page"
          className="inline-flex h-11 min-w-11 sm:h-9 sm:min-w-9 cursor-pointer items-center justify-center rounded-md border border-border bg-surface px-2 text-sm transition-colors duration-200 hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        </button>
        {pages.map((p, i) =>
          p === "…" ? (
            <span
              key={`gap-${i}`}
              className="px-1 text-sm text-cold"
              aria-hidden="true"
            >
              …
            </span>
          ) : (
            <button
              key={p}
              type="button"
              onClick={() => go(p)}
              aria-current={p === safePage ? "page" : undefined}
              className={[
                "num inline-flex h-11 min-w-11 sm:h-9 sm:min-w-9 cursor-pointer items-center justify-center rounded-md border px-2 text-sm transition-colors duration-200",
                p === safePage
                  ? "border-primary bg-primary text-primary-fg"
                  : "border-border bg-surface hover:bg-muted",
              ].join(" ")}
            >
              {p}
            </button>
          ),
        )}
        <button
          type="button"
          onClick={() => go(safePage + 1)}
          disabled={safePage >= totalPages}
          aria-label="Next page"
          className="inline-flex h-11 min-w-11 sm:h-9 sm:min-w-9 cursor-pointer items-center justify-center rounded-md border border-border bg-surface px-2 text-sm transition-colors duration-200 hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </nav>
  );
}

// Build a compact page window: 1 … (p-1) p (p+1) … N
function pageWindow(current: number, total: number): (number | "…")[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }
  const out: (number | "…")[] = [1];
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  if (start > 2) out.push("…");
  for (let p = start; p <= end; p++) out.push(p);
  if (end < total - 1) out.push("…");
  out.push(total);
  return out;
}
