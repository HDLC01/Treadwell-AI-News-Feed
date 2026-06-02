import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  Check,
  ChevronRight,
  Eye,
  Crosshair,
  Loader2,
  MapPin,
  Target,
  Trophy,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import ConfirmDialog from "../components/ConfirmDialog";
import EmptyState from "../components/EmptyState";
import RelevanceIndicator from "../components/RelevanceIndicator";
import { Skeleton } from "../components/Skeleton";
import { getProjects, patchProject, ApiError } from "../lib/api";
import type { ProjectStatus, ProjectSummary } from "../lib/types";
import {
  projectTypeLabel,
  statusLabel,
  locationLine,
  miles,
} from "../lib/format";

// The statuses surfaced in the pipeline, in column order.
const PIPELINE_STATUSES: ProjectStatus[] = [
  "watching",
  "pursuing",
  "won",
  "passed",
];

// Full status vocabulary offered in the per-project <select>.
const ALL_STATUSES: ProjectStatus[] = [
  "new",
  "active",
  "watching",
  "pursuing",
  "won",
  "passed",
  "archived",
  "dismissed",
];

// Status changes that should require an explicit confirm.
const CONFIRM_STATUSES: ProjectStatus[] = ["passed", "archived", "dismissed"];

const SECTION_ICON: Record<string, LucideIcon> = {
  watching: Eye,
  pursuing: Crosshair,
  won: Trophy,
  passed: XCircle,
};

const SECTION_TONE: Record<string, string> = {
  watching: "text-cold",
  pursuing: "text-primary",
  won: "text-primary",
  passed: "text-cold",
};

interface PendingChange {
  project: ProjectSummary;
  next: ProjectStatus;
}

export default function PipelinePage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingChange | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getProjects({ status: PIPELINE_STATUSES.join(","), page_size: 100 })
      .then((res) => {
        if (!cancelled) setProjects(res.items);
      })
      .catch((e) => {
        if (!cancelled) {
          const msg =
            e instanceof ApiError
              ? `Could not load your pipeline (${e.status || "network"}).`
              : "Could not load your pipeline.";
          setError(msg);
          setProjects([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => load(), [load]);

  // Replace a project in local state with the server-returned summary, or drop
  // it if its new status falls outside the pipeline.
  const applyUpdated = useCallback((updated: ProjectSummary) => {
    setProjects((prev) => {
      const inPipeline = PIPELINE_STATUSES.includes(updated.status);
      const exists = prev.some((p) => p.id === updated.id);
      if (!inPipeline) return prev.filter((p) => p.id !== updated.id);
      if (exists) return prev.map((p) => (p.id === updated.id ? updated : p));
      return [...prev, updated];
    });
  }, []);

  // Optimistically reflect a status change locally (keeps row visible if still
  // in pipeline), then reconcile with the server response.
  const commitStatus = useCallback(
    async (project: ProjectSummary, next: ProjectStatus) => {
      setProjects((prev) =>
        prev.map((p) => (p.id === project.id ? { ...p, status: next } : p)),
      );
      try {
        const updated = await patchProject(project.id, { status: next });
        applyUpdated(updated);
      } catch {
        // Revert on failure.
        setProjects((prev) =>
          prev.map((p) =>
            p.id === project.id ? { ...p, status: project.status } : p,
          ),
        );
        setError("Could not update status. Please try again.");
      }
    },
    [applyUpdated],
  );

  const requestStatusChange = useCallback(
    (project: ProjectSummary, next: ProjectStatus) => {
      if (next === project.status) return;
      if (CONFIRM_STATUSES.includes(next)) {
        setPending({ project, next });
      } else {
        void commitStatus(project, next);
      }
    },
    [commitStatus],
  );

  const confirmPending = useCallback(async () => {
    if (!pending) return;
    setConfirmBusy(true);
    await commitStatus(pending.project, pending.next);
    setConfirmBusy(false);
    setPending(null);
  }, [pending, commitStatus]);

  const saveNotes = useCallback(
    async (project: ProjectSummary, notes: string) => {
      const updated = await patchProject(project.id, { notes });
      applyUpdated(updated);
    },
    [applyUpdated],
  );

  // Group projects by status, preserving the API's within-section order.
  const grouped = useMemo(() => {
    const map = new Map<ProjectStatus, ProjectSummary[]>();
    for (const s of PIPELINE_STATUSES) map.set(s, []);
    for (const p of projects) {
      const bucket = map.get(p.status);
      if (bucket) bucket.push(p);
    }
    return map;
  }, [projects]);

  const isEmpty = !loading && !error && projects.length === 0;

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Target className="h-4 w-4" aria-hidden="true" />
        </span>
        <div>
          <h1 className="text-lg font-bold leading-tight text-fg">My Pipeline</h1>
          <p className="text-xs text-cold">
            Projects you are watching, pursuing, won, or passed on.
          </p>
        </div>
      </div>

      {loading ? (
        <PipelineSkeleton />
      ) : error ? (
        <EmptyState
          title="Something went wrong"
          message={`${error} Make sure the backend is running on port 8890, then try again.`}
          icon={AlertCircle}
        />
      ) : isEmpty ? (
        <EmptyState
          title="Nothing in your pipeline yet"
          message="Watch or Pursue projects from the feed."
          icon={Target}
        />
      ) : (
        <div className="space-y-6">
          {PIPELINE_STATUSES.map((s) => {
            const rows = grouped.get(s) ?? [];
            if (rows.length === 0) return null;
            const Icon = SECTION_ICON[s] ?? Target;
            return (
              <section key={s}>
                <div className="sticky top-[57px] z-10 -mx-1 mb-2 flex items-center gap-2 bg-bg/95 px-1 py-1 backdrop-blur">
                  <Icon
                    className={`h-3.5 w-3.5 ${SECTION_TONE[s] ?? "text-cold"}`}
                    aria-hidden="true"
                  />
                  <h2 className="text-xs font-semibold uppercase tracking-wide text-cold">
                    {statusLabel(s)}
                  </h2>
                  <span className="num text-xs text-cold">({rows.length})</span>
                </div>
                <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                  {rows.map((p) => (
                    <PipelineRow
                      key={p.id}
                      project={p}
                      onStatusChange={requestStatusChange}
                      onSaveNotes={saveNotes}
                    />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}

      <ConfirmDialog
        open={pending !== null}
        title={
          pending ? `Move to ${statusLabel(pending.next)}?` : "Move project?"
        }
        message={
          pending
            ? `"${pending.project.title}" will be marked ${statusLabel(
                pending.next,
              ).toLowerCase()} and removed from your active pipeline.`
            : undefined
        }
        confirmLabel={pending ? statusLabel(pending.next) : "Confirm"}
        destructive
        busy={confirmBusy}
        onConfirm={() => void confirmPending()}
        onCancel={() => {
          if (!confirmBusy) setPending(null);
        }}
      />
    </div>
  );
}

// --- A single pipeline row: project facts + notes textarea + status select. ---

function PipelineRow({
  project: p,
  onStatusChange,
  onSaveNotes,
}: {
  project: ProjectSummary;
  onStatusChange: (project: ProjectSummary, next: ProjectStatus) => void;
  onSaveNotes: (project: ProjectSummary, notes: string) => Promise<void>;
}) {
  const [notes, setNotes] = useState(p.notes ?? "");
  const [noteState, setNoteState] = useState<"idle" | "saving" | "saved">(
    "idle",
  );
  // Last value persisted to the server — avoids redundant saves on blur.
  const savedRef = useRef(p.notes ?? "");

  // Keep local notes in sync if the upstream project record changes (e.g. a
  // status move returns a fresh summary) and the field is otherwise untouched.
  useEffect(() => {
    const incoming = p.notes ?? "";
    if (incoming !== savedRef.current) {
      savedRef.current = incoming;
      setNotes(incoming);
    }
  }, [p.notes]);

  const meta = [
    projectTypeLabel(p.project_type),
    p.distance_mi != null ? miles(p.distance_mi) : null,
  ]
    .filter(Boolean)
    .join("  ·  ");

  const handleNotesBlur = useCallback(async () => {
    const trimmed = notes;
    if (trimmed === savedRef.current) return;
    setNoteState("saving");
    try {
      await onSaveNotes(p, trimmed);
      savedRef.current = trimmed;
      setNoteState("saved");
      window.setTimeout(() => setNoteState("idle"), 1800);
    } catch {
      setNoteState("idle");
    }
  }, [notes, onSaveNotes, p]);

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-3.5">
      {/* Header: title + relevance, links to detail */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <Link
            to={`/project/${p.id}`}
            className="group inline-flex items-start gap-1 text-sm font-semibold leading-snug text-fg hover:text-primary"
          >
            <span className="line-clamp-2">{p.title}</span>
            <ChevronRight
              className="mt-0.5 h-4 w-4 shrink-0 text-cold transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-primary"
              aria-hidden="true"
            />
          </Link>
          <p className="mt-0.5 truncate text-xs text-cold">{meta}</p>
        </div>
        <RelevanceIndicator
          tier={p.relevance_tier}
          score={p.relevance_score}
          showScore
          className="shrink-0"
        />
      </div>

      {/* 70-mile priority indicator */}
      {p.within_70mi !== null && (
        <span
          className={`inline-flex w-fit items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium ${
            p.within_70mi ? "bg-primary/10 text-primary" : "bg-muted text-cold"
          }`}
        >
          <MapPin className="h-3 w-3" aria-hidden="true" />
          {p.within_70mi ? "Within 70 mi" : "Outside 70 mi"}
          {(p.city || p.state) && (
            <span className="text-cold">
              {" · "}
              {locationLine(p.city, p.state)}
            </span>
          )}
        </span>
      )}

      {/* Notes — autosave on blur */}
      <div>
        <div className="mb-1 flex items-center justify-between">
          <label
            htmlFor={`notes-${p.id}`}
            className="text-[11px] font-semibold uppercase tracking-wide text-cold"
          >
            Notes
          </label>
          {noteState === "saving" ? (
            <span className="inline-flex items-center gap-1 text-[11px] text-cold">
              <Loader2
                className="h-3 w-3 animate-spin motion-reduce:animate-none"
                aria-hidden="true"
              />
              Saving…
            </span>
          ) : noteState === "saved" ? (
            <span className="inline-flex items-center gap-1 text-[11px] text-primary">
              <Check className="h-3 w-3" aria-hidden="true" />
              Saved
            </span>
          ) : null}
        </div>
        <textarea
          id={`notes-${p.id}`}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={() => void handleNotesBlur()}
          rows={2}
          placeholder="Add a note (saves when you click away)…"
          className="w-full resize-y rounded-md border border-border bg-bg px-2.5 py-1.5 text-xs text-fg placeholder:text-cold focus:border-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </div>

      {/* Status select */}
      <div className="flex items-center justify-between gap-2">
        <label
          htmlFor={`status-${p.id}`}
          className="text-[11px] font-semibold uppercase tracking-wide text-cold"
        >
          Status
        </label>
        <select
          id={`status-${p.id}`}
          value={p.status}
          onChange={(e) =>
            onStatusChange(p, e.target.value as ProjectStatus)
          }
          className="cursor-pointer rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs font-medium text-fg transition-colors duration-200 hover:bg-muted focus:border-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {ALL_STATUSES.map((s) => (
            <option key={s} value={s}>
              {statusLabel(s)}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

function PipelineSkeleton() {
  return (
    <div className="space-y-6">
      {[0, 1].map((s) => (
        <section key={s}>
          <Skeleton className="mb-2 h-4 w-24" />
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {[0, 1].map((i) => (
              <div
                key={i}
                className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-3.5"
              >
                <div className="flex items-start justify-between gap-2">
                  <Skeleton className="h-5 w-2/3" />
                  <Skeleton className="h-5 w-12" />
                </div>
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-12 w-full" />
                <div className="flex justify-between">
                  <Skeleton className="h-4 w-12" />
                  <Skeleton className="h-7 w-24" />
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
