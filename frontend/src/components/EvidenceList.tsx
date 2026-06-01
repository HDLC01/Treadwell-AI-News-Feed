import { ExternalLink, FileText, Newspaper, Megaphone, Building, Zap, Landmark, FileSignature } from "lucide-react";
import type { Signal } from "../lib/types";

/**
 * Renders project signals (evidence) as compact rows:
 * source_name, title (links out), published date, snippet, and a signal_type badge.
 *
 * Label/format helpers are local so this component does not depend on the exact
 * helper names in lib/format.ts.
 */

const SIGNAL_TYPE_LABELS: Record<string, string> = {
  news: "News",
  press_release: "Press Release",
  permit: "Permit",
  utility_filing: "Utility Filing",
  econ_dev_minutes: "Econ Dev Minutes",
  planning_filing: "Planning Filing",
  other: "Other",
};

function signalTypeLabel(t: string): string {
  return SIGNAL_TYPE_LABELS[t] ?? t.replace(/_/g, " ");
}

function SignalIcon({ type }: { type: string }) {
  const cls = "h-3.5 w-3.5 shrink-0";
  switch (type) {
    case "news":
      return <Newspaper className={cls} aria-hidden="true" />;
    case "press_release":
      return <Megaphone className={cls} aria-hidden="true" />;
    case "permit":
      return <FileSignature className={cls} aria-hidden="true" />;
    case "utility_filing":
      return <Zap className={cls} aria-hidden="true" />;
    case "econ_dev_minutes":
      return <Landmark className={cls} aria-hidden="true" />;
    case "planning_filing":
      return <Building className={cls} aria-hidden="true" />;
    default:
      return <FileText className={cls} aria-hidden="true" />;
  }
}

// Local date formatter (absolute, compact). lib/format owns relativeDate; we show
// an absolute date here for evidence provenance clarity.
function formatDate(iso: string | null | undefined): string {
  if (!iso) return "Date unknown";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Date unknown";
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function confidencePct(c: number | null | undefined): string | null {
  if (c === null || c === undefined || Number.isNaN(c)) return null;
  const pct = Math.round(c * 100);
  return `${pct}% conf.`;
}

export function EvidenceList({ signals }: { signals: Signal[] }) {
  const items = signals ?? [];

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-1 rounded-lg border border-border bg-surface py-8 text-center">
        <FileText className="h-6 w-6 text-fg/40" aria-hidden="true" />
        <p className="text-sm font-medium text-fg">No evidence yet</p>
        <p className="text-xs text-fg/60">
          Signals (news, permits, filings) attached to this project will appear here.
        </p>
      </div>
    );
  }

  return (
    <ul className="flex flex-col gap-2">
      {items.map((s) => {
        const conf = confidencePct(s.extraction_confidence);
        return (
          <li
            key={s.id}
            className="rounded-lg border border-border bg-surface p-3 transition-colors duration-150 hover:border-secondary"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1 rounded-full border border-border bg-bg px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-fg/70">
                <SignalIcon type={s.signal_type} />
                {signalTypeLabel(s.signal_type)}
              </span>
              {s.source_name ? (
                <span className="truncate text-xs font-medium text-fg/80" title={s.source_name}>
                  {s.source_name}
                </span>
              ) : null}
              <span className="num ml-auto text-[11px] text-fg/60">{formatDate(s.published_at)}</span>
            </div>

            <div className="mt-1.5">
              {s.url ? (
                <a
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex cursor-pointer items-start gap-1 text-sm font-semibold text-primary hover:underline"
                >
                  <span className="min-w-0">{s.title || "Untitled signal"}</span>
                  <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                </a>
              ) : (
                <span className="text-sm font-semibold text-fg">{s.title || "Untitled signal"}</span>
              )}
            </div>

            {s.snippet ? (
              <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-fg/70">{s.snippet}</p>
            ) : null}

            {conf ? (
              <div className="mt-1.5">
                <span className="num text-[10px] font-medium text-fg/70">{conf}</span>
              </div>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

export default EvidenceList;
