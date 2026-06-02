import { useEffect, useState, useCallback } from "react";
import {
  PlayCircle,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  Database,
  Info,
  ListChecks,
} from "lucide-react";
import type { PipelineRun } from "../lib/types";
import { getRuns, runPipeline } from "../lib/api";

/**
 * Admin page (Agent 2).
 * - Pipeline runs table (most recent first).
 * - "Run pipeline now" button gated by a confirm dialog; calls runPipeline() and shows the
 *   returned note. Handles DEMO_MODE gracefully (the API returns started=false with a note).
 */

interface HealthInfo {
  status?: string;
  env?: string;
  demo_mode?: boolean;
  supabase_configured?: boolean;
  time?: string;
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return (
    d.toLocaleString("en-US", {
      timeZone: "America/Chicago",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }) + " CT"
  );
}

function duration(start: string | null | undefined, end: string | null | undefined): string {
  if (!start || !end) return "—";
  const s = new Date(start).getTime();
  const e = new Date(end).getTime();
  if (Number.isNaN(s) || Number.isNaN(e) || e < s) return "—";
  const secs = Math.round((e - s) / 1000);
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  const r = secs % 60;
  return `${m}m ${r}s`;
}

function StatusBadge({ status }: { status: string }) {
  let color = "var(--cold)";
  let Icon = Clock;
  if (status === "success") {
    color = "var(--hot)";
    Icon = CheckCircle2;
  } else if (status === "failed") {
    color = "var(--destructive)";
    Icon = XCircle;
  } else if (status === "partial") {
    color = "var(--warm)";
    Icon = AlertTriangle;
  } else if (status === "running") {
    color = "var(--secondary)";
    Icon = Loader2;
  }
  // success uses a calmer color than "hot"; override for clarity.
  if (status === "success") color = "#16A34A";
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-0.5 text-[11px] font-semibold capitalize text-fg"
      style={{ color }}
    >
      <Icon
        className={`h-3.5 w-3.5 ${status === "running" ? "animate-spin motion-reduce:animate-none" : ""}`}
        aria-hidden="true"
      />
      {status}
    </span>
  );
}

function errorCount(errors: PipelineRun["errors"]): number {
  if (!errors) return 0;
  if (Array.isArray(errors)) return errors.length;
  return 0;
}

function ConfirmRun({
  open,
  busy,
  demo,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  busy: boolean;
  demo: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <button type="button" aria-label="Cancel" onClick={onCancel} className="absolute inset-0 cursor-pointer bg-black/50" />
      <div className="relative w-full max-w-sm rounded-lg border border-border bg-surface p-4 shadow-xl">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-fg">
          <PlayCircle className="h-5 w-5 text-accent" aria-hidden="true" />
          Run the pipeline now?
        </div>
        <p className="mb-4 text-xs text-fg/70">
          This triggers a manual ingest → extract → cluster → enrich → score run in the background. The
          run-lock prevents overlapping runs.
          {demo ? " In DEMO_MODE no external services are touched." : ""}
        </p>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="inline-flex h-9 cursor-pointer items-center rounded-md border border-border px-3 text-sm font-medium text-fg transition-colors duration-150 hover:bg-muted disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-md bg-accent px-3 text-sm font-semibold text-accent-fg transition-opacity duration-150 hover:opacity-90 disabled:opacity-50"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <PlayCircle className="h-4 w-4" aria-hidden="true" />}
            Run now
          </button>
        </div>
      </div>
    </div>
  );
}

function RunsTableSkeleton() {
  return (
    <div className="animate-pulse motion-reduce:animate-none">
      <div className="mb-2 h-8 rounded bg-muted" />
      {[0, 1, 2, 3, 4].map((i) => (
        <div key={i} className="mb-1.5 h-10 rounded bg-muted" />
      ))}
    </div>
  );
}

export function AdminPage() {
  const [runs, setRuns] = useState<PipelineRun[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [health, setHealth] = useState<HealthInfo | null>(null);

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [noteOk, setNoteOk] = useState(true);

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getRuns();
      setRuns(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load pipeline runs.");
      setRuns(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadHealth = useCallback(async () => {
    try {
      const res = await fetch("/api/health", { headers: { Accept: "application/json" } });
      if (res.ok) setHealth((await res.json()) as HealthInfo);
    } catch {
      /* health is best-effort */
    }
  }, []);

  useEffect(() => {
    void loadRuns();
    void loadHealth();
  }, [loadRuns, loadHealth]);

  const doRun = async () => {
    setRunning(true);
    setNote(null);
    try {
      const res = await runPipeline();
      setNoteOk(!!res?.ok);
      setNote(res?.note ?? (res?.started ? "Pipeline started." : "Pipeline did not start."));
      // refresh the table shortly after a real start
      if (res?.started) {
        setTimeout(() => void loadRuns(), 1200);
      }
    } catch (e) {
      setNoteOk(false);
      setNote(e instanceof Error ? e.message : "Failed to trigger the pipeline.");
    } finally {
      setRunning(false);
      setConfirmOpen(false);
    }
  };

  const demo = !!health?.demo_mode;

  return (
    <div className="mx-auto max-w-5xl px-4 py-4">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-fg">
            <ListChecks className="h-5 w-5 text-secondary" aria-hidden="true" />
            Pipeline Admin
          </h1>
          <p className="mt-1 text-sm text-fg/60">Trigger and monitor the daily project-radar pipeline.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void loadRuns()}
            className="inline-flex h-10 cursor-pointer items-center gap-1.5 rounded-md border border-border bg-surface px-3 text-sm font-medium text-fg transition-colors duration-150 hover:bg-muted"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Refresh
          </button>
          <button
            type="button"
            onClick={() => setConfirmOpen(true)}
            disabled={running}
            className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-accent-fg transition-opacity duration-150 hover:opacity-90 disabled:opacity-60"
          >
            {running ? (
              <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            ) : (
              <PlayCircle className="h-4 w-4" aria-hidden="true" />
            )}
            Run pipeline now
          </button>
        </div>
      </header>

      {/* Environment / DEMO banner */}
      {health ? (
        <div
          className={[
            "mb-4 flex items-center gap-2 rounded-lg border px-3 py-2 text-xs",
            demo ? "border-warm/40 bg-warm/10 text-fg" : "border-border bg-surface text-fg/70",
          ].join(" ")}
        >
          <Database className="h-4 w-4 shrink-0" aria-hidden="true" />
          {demo ? (
            <span>
              <strong>DEMO_MODE</strong> is on — the API serves sample fixtures and the pipeline does not
              touch external services. Set Supabase credentials to run for real.
            </span>
          ) : (
            <span className="num">
              Environment: {health.env ?? "—"} · Supabase {health.supabase_configured ? "configured" : "not configured"}
            </span>
          )}
        </div>
      ) : null}

      {/* Result note from the last run trigger */}
      {note ? (
        <div
          className={[
            "mb-4 flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
            noteOk ? "border-border bg-surface text-fg" : "border-destructive/40 bg-destructive/10 text-fg",
          ].join(" ")}
          role="status"
        >
          {noteOk ? (
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-secondary" aria-hidden="true" />
          ) : (
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
          )}
          <span>{note}</span>
        </div>
      ) : null}

      {/* Runs table */}
      <section className="rounded-lg border border-border bg-surface">
        <div className="border-b border-border px-4 py-2.5">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-fg">
            <Clock className="h-4 w-4" aria-hidden="true" />
            Recent runs
          </h2>
        </div>

        {loading ? (
          <div className="p-4">
            <RunsTableSkeleton />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
            <AlertTriangle className="h-6 w-6 text-destructive" aria-hidden="true" />
            <p className="text-sm font-medium text-fg">Could not load runs</p>
            <p className="text-xs text-fg/60">{error}</p>
            <button
              type="button"
              onClick={() => void loadRuns()}
              className="mt-1 inline-flex h-9 cursor-pointer items-center rounded-md border border-border px-3 text-sm font-medium text-fg transition-colors duration-150 hover:bg-muted"
            >
              Retry
            </button>
          </div>
        ) : !runs || runs.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-1 py-12 text-center">
            <Clock className="h-6 w-6 text-fg/40" aria-hidden="true" />
            <p className="text-sm font-medium text-fg">No pipeline runs yet</p>
            <p className="text-xs text-fg/60">Trigger a run with the button above to see results here.</p>
          </div>
        ) : (
          <>
            {/* Desktop / tablet table */}
            <div className="hidden overflow-x-auto sm:block">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border text-[11px] uppercase tracking-wide text-fg/70">
                    <th className="px-4 py-2 font-semibold">Started</th>
                    <th className="px-4 py-2 font-semibold">Status</th>
                    <th className="px-4 py-2 font-semibold">Trigger</th>
                    <th className="px-4 py-2 text-right font-semibold">Sources</th>
                    <th className="px-4 py-2 text-right font-semibold">Signals</th>
                    <th className="px-4 py-2 text-right font-semibold">Created</th>
                    <th className="px-4 py-2 text-right font-semibold">Updated</th>
                    <th className="px-4 py-2 text-right font-semibold">Duration</th>
                    <th className="px-4 py-2 text-right font-semibold">Errors</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => {
                    const errs = errorCount(r.errors);
                    return (
                      <tr key={r.id} className="border-b border-border/60 last:border-0 hover:bg-muted/30">
                        <td className="num px-4 py-2 text-fg">{formatDateTime(r.started_at)}</td>
                        <td className="px-4 py-2">
                          <StatusBadge status={r.status} />
                        </td>
                        <td className="px-4 py-2 capitalize text-fg/80">{r.trigger}</td>
                        <td className="num px-4 py-2 text-right text-fg">{r.sources_fetched}</td>
                        <td className="num px-4 py-2 text-right text-fg">{r.signals_ingested}</td>
                        <td className="num px-4 py-2 text-right text-fg">{r.projects_created}</td>
                        <td className="num px-4 py-2 text-right text-fg">{r.projects_updated}</td>
                        <td className="num px-4 py-2 text-right text-fg/80">
                          {duration(r.started_at, r.finished_at)}
                        </td>
                        <td className="num px-4 py-2 text-right">
                          {errs > 0 ? (
                            <span className="font-semibold text-destructive">{errs}</span>
                          ) : (
                            <span className="text-fg/40">0</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <ul className="flex flex-col gap-2 p-3 sm:hidden">
              {runs.map((r) => {
                const errs = errorCount(r.errors);
                return (
                  <li key={r.id} className="rounded-md border border-border bg-bg p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="num text-xs font-medium text-fg">{formatDateTime(r.started_at)}</span>
                      <StatusBadge status={r.status} />
                    </div>
                    <div className="mt-2 grid grid-cols-3 gap-2 text-[11px] text-fg/70">
                      <div>
                        <div className="uppercase tracking-wide text-fg/70">Sources</div>
                        <div className="num text-sm font-semibold text-fg">{r.sources_fetched}</div>
                      </div>
                      <div>
                        <div className="uppercase tracking-wide text-fg/70">Signals</div>
                        <div className="num text-sm font-semibold text-fg">{r.signals_ingested}</div>
                      </div>
                      <div>
                        <div className="uppercase tracking-wide text-fg/70">Duration</div>
                        <div className="num text-sm font-semibold text-fg">
                          {duration(r.started_at, r.finished_at)}
                        </div>
                      </div>
                      <div>
                        <div className="uppercase tracking-wide text-fg/70">Created</div>
                        <div className="num text-sm font-semibold text-fg">{r.projects_created}</div>
                      </div>
                      <div>
                        <div className="uppercase tracking-wide text-fg/70">Updated</div>
                        <div className="num text-sm font-semibold text-fg">{r.projects_updated}</div>
                      </div>
                      <div>
                        <div className="uppercase tracking-wide text-fg/70">Errors</div>
                        <div
                          className={`num text-sm font-semibold ${errs > 0 ? "text-destructive" : "text-fg/70"}`}
                        >
                          {errs}
                        </div>
                      </div>
                    </div>
                    <div className="mt-1.5 text-[11px] capitalize text-fg/70">Trigger: {r.trigger}</div>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </section>

      <ConfirmRun
        open={confirmOpen}
        busy={running}
        demo={demo}
        onConfirm={() => void doRun()}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}

export default AdminPage;
