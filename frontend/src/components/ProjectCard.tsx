import { useState } from "react";
import type { MouseEvent } from "react";
import { Link } from "react-router-dom";
import {
  Server,
  Factory,
  HeartPulse,
  GraduationCap,
  Warehouse,
  Wrench,
  ShieldCheck,
  Building,
  ChevronRight,
  MapPin,
  Eye,
  Crosshair,
  Loader2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ProjectStatus, ProjectSummary } from "../lib/types";
import { patchProject } from "../lib/api";
import {
  projectTypeLabel,
  stageLabel,
  locationLine,
  miles,
  megawatts,
  money,
  sqft,
  relativeDate,
  roleLabel,
  confidenceLabelText,
} from "../lib/format";
import RelevanceIndicator from "./RelevanceIndicator";

interface Props {
  project: ProjectSummary;
}

const TYPE_ICON: Record<string, LucideIcon> = {
  data_center: Server,
  industrial: Factory,
  healthcare: HeartPulse,
  higher_ed: GraduationCap,
  distribution: Warehouse,
  manufacturing: Wrench,
  mission_critical: ShieldCheck,
  other_commercial: Building,
};

// Confidence shown as quiet colored text rather than another chip.
const CONFIDENCE_TEXT: Record<string, string> = {
  confirmed: "text-primary",
  likely: "text-warm-text",
  rumored: "text-cold",
};

// A project-first OPPORTUNITY card. Deliberately calm: ONE accent (relevance),
// a quiet metadata line, the team line (who to chase) as the single highlighted
// element, then quiet facts and a muted footer. No competing badge row.
export default function ProjectCard({ project: p }: Props) {
  const Icon = TYPE_ICON[p.project_type] ?? Building;
  const isDataCenter = p.project_type === "data_center";
  const top = p.top_team_member;

  // Quick-triage state: optimistic status + in-flight guard, so Kyle can Watch
  // or Pursue a project straight from the feed without opening it.
  const [status, setStatus] = useState<ProjectStatus>(p.status);
  const [saving, setSaving] = useState<ProjectStatus | null>(null);

  const triage = async (
    e: MouseEvent<HTMLButtonElement>,
    next: ProjectStatus,
  ) => {
    // Stop the card's Link from navigating.
    e.preventDefault();
    e.stopPropagation();
    if (saving) return;
    const prev = status;
    setStatus(next);
    setSaving(next);
    try {
      const updated = await patchProject(p.id, { status: next });
      setStatus(updated?.status ?? next);
    } catch {
      setStatus(prev);
    } finally {
      setSaving(null);
    }
  };

  // Quiet metadata: type · stage · location · distance (only what exists).
  const meta = [
    projectTypeLabel(p.project_type),
    p.stage ? stageLabel(p.stage) : null,
    p.city || p.state ? locationLine(p.city, p.state) : null,
    p.distance_mi != null ? miles(p.distance_mi) : null,
  ]
    .filter(Boolean)
    .join("  ·  ");

  // Quiet facts: only present values (MW only matters for data centers).
  const facts: string[] = [];
  if (isDataCenter && p.est_megawatts != null) facts.push(megawatts(p.est_megawatts));
  if (p.est_value_usd != null) facts.push(money(p.est_value_usd));
  if (p.est_sqft != null) facts.push(sqft(p.est_sqft));

  return (
    <Link
      to={`/project/${p.id}`}
      className="group flex h-full cursor-pointer flex-col gap-3 rounded-xl border border-border bg-surface p-4 transition-all duration-200 hover:border-primary/40 hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {/* Header: type icon + title + relevance */}
      <div className="flex items-start gap-3">
        <span
          className={`mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
            isDataCenter ? "bg-primary/10 text-primary" : "bg-muted text-cold"
          }`}
        >
          <Icon className="h-4 w-4" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <h3 className="line-clamp-2 text-sm font-semibold leading-snug text-fg group-hover:text-primary">
              {p.title}
            </h3>
            <RelevanceIndicator
              tier={p.relevance_tier}
              score={p.relevance_score}
              showScore
              className="shrink-0"
            />
          </div>
          <p className="mt-1 truncate text-xs text-cold">{meta}</p>
        </div>
      </div>

      {/* 70-mile priority indicator (the office service radius) */}
      {p.within_70mi !== null && (
        <span
          className={`inline-flex w-fit items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium ${
            p.within_70mi ? "bg-primary/10 text-primary" : "bg-muted text-cold"
          }`}
        >
          <MapPin className="h-3 w-3" aria-hidden="true" />
          {p.within_70mi ? "Within 70 mi" : "Outside 70 mi"}
        </span>
      )}

      {/* Team line — the one highlighted element: who to get in front of */}
      {top ? (
        <div className="flex items-center justify-between gap-2 rounded-lg bg-muted/50 px-2.5 py-1.5">
          <span className="min-w-0 truncate text-xs">
            <span className="text-cold">{roleLabel(top.role)} · </span>
            <span className="font-medium text-fg">{top.company_name}</span>
          </span>
          <span
            className={`shrink-0 text-[11px] font-medium ${
              CONFIDENCE_TEXT[top.confidence_label] ?? "text-cold"
            }`}
          >
            {confidenceLabelText(top.confidence_label)}
          </span>
        </div>
      ) : (
        <div className="rounded-lg bg-muted/40 px-2.5 py-1.5 text-xs text-cold">
          Team not yet identified
        </div>
      )}

      {/* Quiet facts (only present) */}
      {facts.length > 0 && (
        <p className="num truncate text-xs text-fg/70">{facts.join("   ·   ")}</p>
      )}

      {/* Quick triage: Watch / Pursue without leaving the feed */}
      <div className="flex items-center gap-1.5">
        <TriageButton
          label="Watch"
          icon={Eye}
          active={status === "watching"}
          busy={saving === "watching"}
          disabled={saving !== null}
          onClick={(e) => void triage(e, "watching")}
        />
        <TriageButton
          label="Pursue"
          icon={Crosshair}
          active={status === "pursuing"}
          busy={saving === "pursuing"}
          disabled={saving !== null}
          onClick={(e) => void triage(e, "pursuing")}
        />
      </div>

      {/* Muted footer: evidence + recency + affordance */}
      <div className="mt-auto flex items-center justify-between gap-2 pt-1 text-xs text-cold">
        <span className="truncate">
          <span className="num">{p.signals_count}</span>{" "}
          {p.signals_count === 1 ? "source" : "sources"}
          {"  ·  "}
          {relativeDate(p.last_signal_at)}
        </span>
        <ChevronRight
          className="h-4 w-4 shrink-0 transition-transform duration-200 group-hover:translate-x-0.5"
          aria-hidden="true"
        />
      </div>
    </Link>
  );
}

// Small inline triage chip used on the feed card. Reflects the current status
// (filled when active) and shows a spinner while the PATCH is in flight.
function TriageButton({
  label,
  icon: Icon,
  active,
  busy,
  disabled,
  onClick,
}: {
  label: string;
  icon: LucideIcon;
  active: boolean;
  busy: boolean;
  disabled: boolean;
  onClick: (e: MouseEvent<HTMLButtonElement>) => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className={[
        "inline-flex h-11 cursor-pointer items-center gap-1.5 rounded-md border px-3 text-xs font-medium transition-colors duration-200 disabled:opacity-60 sm:h-9",
        active
          ? "border-primary bg-primary/10 text-primary"
          : "border-border text-cold hover:bg-muted hover:text-fg",
      ].join(" ")}
    >
      {busy ? (
        <Loader2
          className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none"
          aria-hidden="true"
        />
      ) : (
        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      )}
      {label}
    </button>
  );
}
