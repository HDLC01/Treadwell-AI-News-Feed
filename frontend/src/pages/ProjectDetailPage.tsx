import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import {
  ArrowLeft,
  MapPin,
  Gauge,
  DollarSign,
  Ruler,
  Zap,
  Users,
  FileText,
  Phone,
  AlertTriangle,
  CheckCircle2,
  Eye,
  Crosshair,
  Trophy,
  XCircle,
  Archive,
  Ban,
  Check,
  StickyNote,
  Loader2,
} from "lucide-react";
import type { ProjectDetail, Signal } from "../lib/types";
import { getProject, getProjectSignals, patchProject } from "../lib/api";
import { TeamHierarchy } from "../components/TeamHierarchy";
import { EvidenceList } from "../components/EvidenceList";
import { ContactsDrawer } from "../components/ContactsDrawer";

/**
 * Project detail page (Agent 2).
 * Header (title/type/stage/distance/in-radius/relevance), TeamHierarchy, key facts
 * (MW/$/sqft), tabs Overview + Evidence, prominent Contacts button (opens ContactsDrawer),
 * status control with a confirm dialog on the destructive "dismiss" action, loading
 * skeleton, and a back link to the feed.
 *
 * Label/format helpers and small UI primitives are local so this page compiles
 * independently of the scaffold's exact component prop signatures, while still using
 * the api client + shared types (the firm contracts).
 */

const PROJECT_TYPE_LABELS: Record<string, string> = {
  data_center: "Data Center",
  industrial: "Industrial",
  healthcare: "Healthcare",
  higher_ed: "Higher Ed",
  distribution: "Distribution",
  manufacturing: "Manufacturing",
  mission_critical: "Mission Critical",
  other_commercial: "Other Commercial",
};

const STAGE_LABELS: Record<string, string> = {
  rumored: "Rumored",
  planning: "Planning",
  design: "Design",
  permitting: "Permitting",
  procurement: "Procurement",
  pre_bid: "Pre-Bid",
  under_construction: "Under Construction",
  complete: "Complete",
  dead: "Dead",
};

const TIER_LABELS: Record<string, string> = { hot: "Hot", warm: "Warm", cold: "Cold" };

type StatusValue =
  | "active"
  | "watching"
  | "pursuing"
  | "won"
  | "passed"
  | "dismissed";

const STATUS_OPTIONS: { value: StatusValue; label: string; icon: typeof Eye; destructive?: boolean }[] = [
  { value: "active", label: "Active", icon: CheckCircle2 },
  { value: "watching", label: "Watching", icon: Eye },
  { value: "pursuing", label: "Pursuing", icon: Crosshair },
  { value: "won", label: "Won", icon: Trophy },
  { value: "passed", label: "Passed", icon: XCircle },
  { value: "dismissed", label: "Dismiss", icon: Ban, destructive: true },
];

function typeLabel(t: string): string {
  return PROJECT_TYPE_LABELS[t] ?? t.replace(/_/g, " ");
}
function stageLabel(s: string | null | undefined): string {
  if (!s) return "Stage unknown";
  return STAGE_LABELS[s] ?? s.replace(/_/g, " ");
}
function tierColor(tier: string | null | undefined): string {
  if (tier === "hot") return "var(--hot)";
  if (tier === "warm") return "var(--warm)";
  return "var(--cold)";
}
function fmtMiles(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${n.toFixed(0)} mi`;
}
function fmtMoney(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n) || n <= 0) return "—";
  if (n >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(2)}B`;
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}
function fmtMw(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n) || n <= 0) return "—";
  return `${n.toLocaleString()} MW`;
}
function fmtSqft(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n) || n <= 0) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M sqft`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K sqft`;
  return `${n.toLocaleString()} sqft`;
}
function locationLine(p: ProjectDetail): string {
  const parts = [p.city, p.state].filter(Boolean);
  const base = parts.join(", ");
  if (p.county) return base ? `${base} · ${p.county} County` : `${p.county} County`;
  return base || "Location unknown";
}

// --- Local UI primitives (self-contained) ---

function StatPill({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Zap;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2">
      <Icon className="h-4 w-4 shrink-0 text-secondary" aria-hidden="true" />
      <div className="min-w-0">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-fg/70">{label}</div>
        <div className="num text-sm font-semibold text-fg">{value}</div>
      </div>
    </div>
  );
}

function ConfirmDismiss({
  open,
  title,
  busy,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  busy: boolean;
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
      <button
        type="button"
        aria-label="Cancel"
        onClick={onCancel}
        className="absolute inset-0 cursor-pointer bg-black/50"
      />
      <div className="relative w-full max-w-sm rounded-lg border border-border bg-surface p-4 shadow-xl">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-fg">
          <AlertTriangle className="h-5 w-5 text-destructive" aria-hidden="true" />
          Dismiss this project?
        </div>
        <p className="mb-4 text-xs text-fg/70">
          “{title}” will be marked dismissed and hidden from the default feed. You can still find it by
          filtering for dismissed projects.
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
            className="inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-md bg-destructive px-3 text-sm font-semibold text-destructive-fg transition-opacity duration-150 hover:opacity-90 disabled:opacity-50"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <Ban className="h-4 w-4" aria-hidden="true" />}
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="mx-auto max-w-5xl animate-pulse px-4 py-4 motion-reduce:animate-none">
      <div className="mb-4 h-4 w-28 rounded bg-muted" />
      <div className="mb-3 h-7 w-3/4 rounded bg-muted" />
      <div className="mb-6 flex gap-2">
        <div className="h-6 w-24 rounded-full bg-muted" />
        <div className="h-6 w-24 rounded-full bg-muted" />
        <div className="h-6 w-20 rounded-full bg-muted" />
      </div>
      <div className="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-14 rounded-lg bg-muted" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="h-64 rounded-lg bg-muted lg:col-span-2" />
        <div className="h-64 rounded-lg bg-muted" />
      </div>
    </div>
  );
}

export function ProjectDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"overview" | "evidence">("overview");
  const [contactsOpen, setContactsOpen] = useState(false);
  const [savingStatus, setSavingStatus] = useState<StatusValue | null>(null);
  const [confirmDismiss, setConfirmDismiss] = useState(false);
  const [notes, setNotes] = useState("");
  const [notesState, setNotesState] = useState<"idle" | "saving" | "saved">("idle");
  // Last notes value persisted to the server — avoids redundant saves on blur.
  const savedNotesRef = useRef("");

  const loadProject = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const p = await getProject(id);
      setProject(p);
      setNotes(p.notes ?? "");
      savedNotesRef.current = p.notes ?? "";
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load project.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  const loadSignals = useCallback(async () => {
    try {
      const s = await getProjectSignals(id);
      setSignals(Array.isArray(s) ? s : []);
    } catch {
      setSignals([]);
    }
  }, [id]);

  useEffect(() => {
    if (!id) return;
    void loadProject();
    void loadSignals();
  }, [id, loadProject, loadSignals]);

  const applyStatus = async (status: StatusValue) => {
    setSavingStatus(status);
    try {
      const updated = await patchProject(id, { status });
      const nextStatus = updated?.status ?? status;
      setProject((prev) => (prev ? { ...prev, status: nextStatus } : prev));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update status.");
    } finally {
      setSavingStatus(null);
      setConfirmDismiss(false);
    }
  };

  const onStatusClick = (status: StatusValue, destructive?: boolean) => {
    if (destructive) {
      setConfirmDismiss(true);
    } else {
      void applyStatus(status);
    }
  };

  // Autosave notes on blur (skips when unchanged from the last persisted value).
  const saveNotes = useCallback(async () => {
    if (notes === savedNotesRef.current) return;
    const value = notes;
    setNotesState("saving");
    try {
      const updated = await patchProject(id, { notes: value });
      const nextNotes = updated?.notes ?? value;
      savedNotesRef.current = nextNotes;
      setProject((prev) => (prev ? { ...prev, notes: nextNotes } : prev));
      setNotesState("saved");
      window.setTimeout(() => setNotesState("idle"), 1800);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save notes.");
      setNotesState("idle");
    }
  }, [id, notes]);

  if (loading) return <DetailSkeleton />;

  if (error || !project) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-12">
        <Link
          to="/"
          className="mb-6 inline-flex cursor-pointer items-center gap-1 text-sm font-medium text-secondary hover:underline"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back to feed
        </Link>
        <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-border bg-surface py-12 text-center">
          <AlertTriangle className="h-7 w-7 text-destructive" aria-hidden="true" />
          <p className="text-sm font-medium text-fg">Could not load this project</p>
          <p className="text-xs text-fg/60">{error ?? "Project not found."}</p>
          <button
            type="button"
            onClick={() => void loadProject()}
            className="mt-1 inline-flex h-9 cursor-pointer items-center rounded-md border border-border px-3 text-sm font-medium text-fg transition-colors duration-150 hover:bg-muted"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const reasoning = project.relevance_reasoning;
  const reasoningText =
    typeof reasoning === "string"
      ? reasoning
      : reasoning && typeof reasoning === "object"
        ? (reasoning as Record<string, unknown>).summary ??
          (reasoning as Record<string, unknown>).reasoning ??
          null
        : null;
  const reasoningFactors =
    reasoning && typeof reasoning === "object" && Array.isArray((reasoning as Record<string, unknown>).factors)
      ? ((reasoning as Record<string, unknown>).factors as unknown[]).map(String)
      : [];

  return (
    <div className="mx-auto max-w-5xl px-4 py-4">
      <Link
        to="/"
        className="mb-4 inline-flex cursor-pointer items-center gap-1 text-sm font-medium text-secondary hover:underline"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to feed
      </Link>

      {/* Header */}
      <header className="mb-5">
        <h1 className="text-xl font-bold leading-tight text-fg sm:text-2xl">{project.title}</h1>

        <div className="mt-2 flex flex-wrap items-center gap-2">
          {/* type */}
          <span className="rounded-full border border-border bg-surface px-2.5 py-1 text-xs font-semibold text-fg">
            {typeLabel(project.project_type)}
          </span>
          {/* stage */}
          <span className="rounded-full border border-border bg-muted px-2.5 py-1 text-xs font-medium text-fg">
            {stageLabel(project.stage)}
          </span>
          {/* relevance */}
          <span
            className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs font-semibold text-fg"
            title={`Relevance ${project.relevance_score ?? 0}/100`}
          >
            <Gauge className="h-3.5 w-3.5" aria-hidden="true" />
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: tierColor(project.relevance_tier) }}
              aria-hidden="true"
            />
            {TIER_LABELS[project.relevance_tier ?? "cold"] ?? "Cold"}
            <span className="num">· {project.relevance_score ?? 0}</span>
          </span>
          {/* distance + radius */}
          <span className="num inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-xs font-medium text-fg">
            <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
            {fmtMiles(project.distance_mi)}
          </span>
          {project.within_70mi ? (
            <span className="inline-flex items-center gap-1 rounded-full border border-border bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
              <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
              Within 70 mi
            </span>
          ) : project.within_70mi === false ? (
            <span className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-xs font-medium text-fg/60">
              Outside 70 mi
            </span>
          ) : null}
        </div>

        <p className="mt-2 flex items-center gap-1 text-sm text-fg/70">
          <MapPin className="h-4 w-4 shrink-0" aria-hidden="true" />
          {locationLine(project)}
          {project.address ? <span className="text-fg/70"> — {project.address}</span> : null}
        </p>

        {/* Action bar */}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setContactsOpen(true)}
            className="inline-flex h-11 cursor-pointer items-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-accent-fg transition-opacity duration-150 hover:opacity-90"
          >
            <Phone className="h-4 w-4" aria-hidden="true" />
            Contacts
            {typeof project.contacts_count === "number" ? (
              <span className="num rounded-full bg-white/25 px-1.5 text-xs">{project.contacts_count}</span>
            ) : null}
          </button>

          {/* Status control */}
          <div className="flex flex-wrap items-center gap-1 rounded-md border border-border bg-surface p-1">
            {STATUS_OPTIONS.map((opt) => {
              const active = project.status === opt.value;
              const Icon = opt.icon;
              const busy = savingStatus === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => onStatusClick(opt.value, opt.destructive)}
                  disabled={!!savingStatus}
                  aria-pressed={active}
                  className={[
                    "inline-flex h-9 cursor-pointer items-center gap-1.5 rounded px-2.5 text-xs font-semibold transition-colors duration-150 disabled:opacity-60",
                    active
                      ? opt.destructive
                        ? "bg-destructive text-destructive-fg"
                        : "bg-primary text-primary-fg"
                      : "text-fg/70 hover:bg-muted",
                  ].join(" ")}
                  title={opt.label}
                >
                  {busy ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                  ) : (
                    <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                  )}
                  {opt.label}
                </button>
              );
            })}
          </div>

          {project.status === "archived" ? (
            <span className="inline-flex items-center gap-1 text-xs text-fg/60">
              <Archive className="h-3.5 w-3.5" aria-hidden="true" />
              Archived
            </span>
          ) : null}
        </div>
      </header>

      {/* Key facts */}
      <div className="mb-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <StatPill icon={Zap} label="Power" value={fmtMw(project.est_megawatts)} />
        <StatPill icon={DollarSign} label="Est. Value" value={fmtMoney(project.est_value_usd)} />
        <StatPill icon={Ruler} label="Size" value={fmtSqft(project.est_sqft)} />
        <StatPill
          icon={FileText}
          label="Signals"
          value={String(project.signals_count ?? signals.length ?? 0)}
        />
      </div>

      {/* Tabs */}
      <div className="mb-3 flex gap-1 border-b border-border">
        <button
          type="button"
          onClick={() => setTab("overview")}
          aria-selected={tab === "overview"}
          className={[
            "inline-flex cursor-pointer items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-semibold transition-colors duration-150",
            tab === "overview" ? "border-primary text-primary" : "border-transparent text-fg/60 hover:text-fg",
          ].join(" ")}
        >
          <Gauge className="h-4 w-4" aria-hidden="true" />
          Overview
        </button>
        <button
          type="button"
          onClick={() => setTab("evidence")}
          aria-selected={tab === "evidence"}
          className={[
            "inline-flex cursor-pointer items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-semibold transition-colors duration-150",
            tab === "evidence" ? "border-primary text-primary" : "border-transparent text-fg/60 hover:text-fg",
          ].join(" ")}
        >
          <FileText className="h-4 w-4" aria-hidden="true" />
          Evidence
          <span className="num rounded-full bg-muted px-1.5 text-xs text-fg/70">{signals.length}</span>
        </button>
      </div>

      {tab === "overview" ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="flex min-w-0 flex-col gap-4 lg:col-span-2">
            <section className="rounded-lg border border-border bg-surface p-4">
              <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold text-fg">
                <FileText className="h-4 w-4" aria-hidden="true" />
                Summary
              </h2>
              {project.summary ? (
                <p className="text-sm leading-relaxed text-fg/80">{project.summary}</p>
              ) : (
                <p className="text-sm text-fg/70">No summary available yet.</p>
              )}
            </section>

            <section className="rounded-lg border border-border bg-surface p-4">
              <div className="mb-2 flex items-center justify-between">
                <h2 className="flex items-center gap-2 text-sm font-semibold text-fg">
                  <StickyNote className="h-4 w-4" aria-hidden="true" />
                  Notes
                </h2>
                {notesState === "saving" ? (
                  <span className="inline-flex items-center gap-1 text-xs text-fg/60">
                    <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                    Saving…
                  </span>
                ) : notesState === "saved" ? (
                  <span className="inline-flex items-center gap-1 text-xs text-primary">
                    <Check className="h-3.5 w-3.5" aria-hidden="true" />
                    Saved
                  </span>
                ) : null}
              </div>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                onBlur={() => void saveNotes()}
                rows={4}
                placeholder="Private notes for this project (saves when you click away)…"
                className="w-full resize-y rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg placeholder:text-fg/40 focus:border-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </section>

            <section className="rounded-lg border border-border bg-surface p-4">
              <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold text-fg">
                <Gauge className="h-4 w-4" aria-hidden="true" />
                Why this scored {project.relevance_score ?? 0}
              </h2>
              {reasoningText ? (
                <p className="text-sm leading-relaxed text-fg/80">{String(reasoningText)}</p>
              ) : null}
              {reasoningFactors.length > 0 ? (
                <ul className="mt-2 list-inside list-disc text-sm text-fg/75">
                  {reasoningFactors.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              ) : null}
              {!reasoningText && reasoningFactors.length === 0 ? (
                <p className="text-sm text-fg/70">No scoring rationale recorded.</p>
              ) : null}
            </section>
          </div>

          <div className="flex min-w-0 flex-col gap-4">
            <TeamHierarchy team={project.team ?? []} teamConfidence={project.team_confidence} />
            <button
              type="button"
              onClick={() => setContactsOpen(true)}
              className="inline-flex h-11 w-full cursor-pointer items-center justify-center gap-2 rounded-md border border-border bg-surface px-4 text-sm font-semibold text-fg transition-colors duration-150 hover:bg-muted"
            >
              <Users className="h-4 w-4" aria-hidden="true" />
              View contacts
            </button>
          </div>
        </div>
      ) : (
        <EvidenceList signals={signals} />
      )}

      <ContactsDrawer
        projectId={id}
        projectTitle={project.title}
        open={contactsOpen}
        onClose={() => setContactsOpen(false)}
      />

      <ConfirmDismiss
        open={confirmDismiss}
        title={project.title}
        busy={savingStatus === "dismissed"}
        onConfirm={() => void applyStatus("dismissed")}
        onCancel={() => setConfirmDismiss(false)}
      />
    </div>
  );
}

export default ProjectDetailPage;
