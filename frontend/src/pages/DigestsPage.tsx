import { useEffect, useState, useCallback } from "react";
import {
  Mail,
  Calendar,
  ArrowLeft,
  Sparkles,
  RefreshCw,
  AlertTriangle,
  Loader2,
  Inbox,
  ChevronRight,
} from "lucide-react";
import type { DigestSummary } from "../lib/types";
import { getDigests, getDigest } from "../lib/api";

/**
 * Digests page (Agent 2).
 * Lists past daily digests (date, new/updated counts). Selecting one fetches and renders
 * its html_body inside a sandboxed <iframe> (full isolation from the app — no scripts,
 * no same-origin) so untrusted email HTML can never touch the host page.
 */

interface OpenDigest {
  digest_date: string;
  html_body?: string | null;
  project_ids?: string[];
  new_count?: number;
  updated_count?: number;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "Unknown date";
  // digest_date is a date string (YYYY-MM-DD); parse safely.
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) {
    const d2 = new Date(iso);
    if (Number.isNaN(d2.getTime())) return iso;
    return d2.toLocaleDateString("en-US", { weekday: "short", year: "numeric", month: "long", day: "numeric" });
  }
  return d.toLocaleDateString("en-US", { weekday: "short", year: "numeric", month: "long", day: "numeric" });
}

function DigestListSkeleton() {
  return (
    <ul className="flex animate-pulse flex-col gap-2 motion-reduce:animate-none">
      {[0, 1, 2, 3].map((i) => (
        <li key={i} className="h-20 rounded-lg bg-muted" />
      ))}
    </ul>
  );
}

export function DigestsPage() {
  const [digests, setDigests] = useState<DigestSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [open, setOpen] = useState<OpenDigest | null>(null);
  const [openLoading, setOpenLoading] = useState(false);
  const [openError, setOpenError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getDigests();
      setDigests(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load digests.");
      setDigests(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openOne = async (date: string) => {
    setOpenLoading(true);
    setOpenError(null);
    setOpen({ digest_date: date });
    try {
      const d = await getDigest(date);
      setOpen({
        digest_date: d.digest_date ?? date,
        html_body: d.html_body,
        project_ids: d.project_ids,
        new_count: d.new_count,
        updated_count: d.updated_count,
      });
    } catch (e) {
      setOpenError(e instanceof Error ? e.message : "Failed to load this digest.");
    } finally {
      setOpenLoading(false);
    }
  };

  // --- Detail view (a selected digest) ---
  if (open) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-4">
        <button
          type="button"
          onClick={() => setOpen(null)}
          className="mb-4 inline-flex cursor-pointer items-center gap-1 text-sm font-medium text-secondary hover:underline"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          All digests
        </button>

        <header className="mb-4">
          <h1 className="flex items-center gap-2 text-xl font-bold text-fg">
            <Mail className="h-5 w-5 text-accent" aria-hidden="true" />
            {formatDate(open.digest_date)}
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-fg/70">
            {typeof open.new_count === "number" ? (
              <span className="num inline-flex items-center gap-1 rounded-full border border-border bg-surface px-2 py-0.5">
                <Sparkles className="h-3 w-3 text-accent" aria-hidden="true" />
                {open.new_count} new
              </span>
            ) : null}
            {typeof open.updated_count === "number" ? (
              <span className="num inline-flex items-center gap-1 rounded-full border border-border bg-surface px-2 py-0.5">
                <RefreshCw className="h-3 w-3 text-secondary" aria-hidden="true" />
                {open.updated_count} updated
              </span>
            ) : null}
            {open.project_ids ? (
              <span className="num inline-flex items-center gap-1 rounded-full border border-border bg-surface px-2 py-0.5">
                {open.project_ids.length} projects
              </span>
            ) : null}
          </div>
        </header>

        {openLoading ? (
          <div className="flex items-center justify-center gap-2 rounded-lg border border-border bg-surface py-16 text-sm text-fg/60">
            <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            Rendering digest…
          </div>
        ) : openError ? (
          <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-border bg-surface py-16 text-center">
            <AlertTriangle className="h-6 w-6 text-destructive" aria-hidden="true" />
            <p className="text-sm font-medium text-fg">Could not load this digest</p>
            <p className="text-xs text-fg/60">{openError}</p>
            <button
              type="button"
              onClick={() => void openOne(open.digest_date)}
              className="mt-1 inline-flex h-9 cursor-pointer items-center rounded-md border border-border px-3 text-sm font-medium text-fg transition-colors duration-150 hover:bg-muted"
            >
              Retry
            </button>
          </div>
        ) : open.html_body ? (
          <div className="overflow-hidden rounded-lg border border-border bg-white">
            {/* Sandboxed: no scripts, no same-origin access to the host app. */}
            <iframe
              title={`Digest ${open.digest_date}`}
              sandbox=""
              srcDoc={open.html_body}
              className="h-[70vh] w-full"
            />
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center gap-1 rounded-lg border border-border bg-surface py-16 text-center">
            <Inbox className="h-6 w-6 text-fg/40" aria-hidden="true" />
            <p className="text-sm font-medium text-fg">This digest has no rendered HTML body</p>
            {open.project_ids && open.project_ids.length > 0 ? (
              <p className="num text-xs text-fg/60">{open.project_ids.length} projects were included.</p>
            ) : null}
          </div>
        )}
      </div>
    );
  }

  // --- List view ---
  return (
    <div className="mx-auto max-w-3xl px-4 py-4">
      <header className="mb-4">
        <h1 className="flex items-center gap-2 text-xl font-bold text-fg">
          <Mail className="h-5 w-5 text-accent" aria-hidden="true" />
          Daily Digests
        </h1>
        <p className="mt-1 text-sm text-fg/60">
          Past project radar digests — each one a snapshot of new and updated opportunities.
        </p>
      </header>

      {loading ? (
        <DigestListSkeleton />
      ) : error ? (
        <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-border bg-surface py-12 text-center">
          <AlertTriangle className="h-6 w-6 text-destructive" aria-hidden="true" />
          <p className="text-sm font-medium text-fg">Could not load digests</p>
          <p className="text-xs text-fg/60">{error}</p>
          <button
            type="button"
            onClick={() => void load()}
            className="mt-1 inline-flex h-9 cursor-pointer items-center rounded-md border border-border px-3 text-sm font-medium text-fg transition-colors duration-150 hover:bg-muted"
          >
            Retry
          </button>
        </div>
      ) : !digests || digests.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-1 rounded-lg border border-border bg-surface py-12 text-center">
          <Inbox className="h-6 w-6 text-fg/40" aria-hidden="true" />
          <p className="text-sm font-medium text-fg">No digests yet</p>
          <p className="text-xs text-fg/60">
            Digests are generated by the daily pipeline. Run it from the Admin page to create one.
          </p>
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {digests.map((d) => (
            <li key={d.digest_date}>
              <button
                type="button"
                onClick={() => void openOne(d.digest_date)}
                className="flex w-full cursor-pointer items-center gap-3 rounded-lg border border-border bg-surface p-3 text-left transition-colors duration-150 hover:border-secondary hover:bg-muted/40"
              >
                <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-muted text-secondary">
                  <Calendar className="h-5 w-5" aria-hidden="true" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold text-fg">{formatDate(d.digest_date)}</div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-fg/60">
                    <span className="num inline-flex items-center gap-1">
                      <Sparkles className="h-3 w-3 text-accent" aria-hidden="true" />
                      {d.new_count} new
                    </span>
                    <span className="num inline-flex items-center gap-1">
                      <RefreshCw className="h-3 w-3 text-secondary" aria-hidden="true" />
                      {d.updated_count} updated
                    </span>
                    <span className="num inline-flex items-center gap-1">{d.project_count} projects</span>
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-fg/40" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default DigestsPage;
