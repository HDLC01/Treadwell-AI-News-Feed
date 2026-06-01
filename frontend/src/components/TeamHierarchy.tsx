import { Building2, HardHat, Landmark, Cloud, Users } from "lucide-react";
import type { TeamMember } from "../lib/types";

/**
 * Renders the project team as a hierarchy: General Contractor > Developer > Owner > others.
 * Each member shows role, company, confidence_label, and a hyperscaler flag.
 * When the team is empty, shows a clear "Team not yet identified" empty state.
 *
 * Label maps are defined locally so this component does not depend on the exact
 * helper-function names in lib/format.ts (which the scaffold owns).
 */

// Desired display order for roles (lower index = higher priority).
const ROLE_ORDER: Record<string, number> = {
  general_contractor: 0,
  developer: 1,
  owner: 2,
  end_user: 3,
  construction_manager: 4,
  architect: 5,
  engineer: 6,
  utility: 7,
  other: 8,
};

const ROLE_LABELS: Record<string, string> = {
  general_contractor: "General Contractor",
  developer: "Developer",
  owner: "Owner",
  end_user: "End User",
  construction_manager: "Construction Manager",
  architect: "Architect",
  engineer: "Engineer",
  utility: "Utility",
  other: "Other",
};

const CONFIDENCE_LABELS: Record<string, string> = {
  confirmed: "Confirmed",
  likely: "Likely",
  rumored: "Rumored",
};

const TEAM_CONFIDENCE_LABELS: Record<string, string> = {
  gc_named: "GC named",
  developer_named: "Developer named",
  owner_only: "Owner only",
  unknown: "Unknown",
};

// Inline team-confidence chip (self-contained — no dependency on the scaffold's badge).
function TeamConfidenceChip({ confidence }: { confidence: string }) {
  const label = TEAM_CONFIDENCE_LABELS[confidence] ?? confidence.replace(/_/g, " ");
  const color =
    confidence === "gc_named"
      ? "var(--hot)"
      : confidence === "developer_named"
        ? "var(--warm)"
        : confidence === "owner_only"
          ? "var(--secondary)"
          : "var(--cold)";
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-0.5 text-[11px] font-medium text-fg"
      title={`Team confidence: ${label}`}
    >
      <span
        className="inline-block h-2 w-2 rounded-full"
        style={{ backgroundColor: color }}
        aria-hidden="true"
      />
      {label}
    </span>
  );
}

function roleRank(role: string): number {
  return role in ROLE_ORDER ? ROLE_ORDER[role] : 99;
}

function roleText(role: string): string {
  return ROLE_LABELS[role] ?? role.replace(/_/g, " ");
}

function confidenceText(label: string): string {
  return CONFIDENCE_LABELS[label] ?? label.replace(/_/g, " ");
}

function RoleIcon({ role }: { role: string }) {
  const cls = "h-4 w-4 shrink-0";
  switch (role) {
    case "general_contractor":
      return <HardHat className={cls} aria-hidden="true" />;
    case "developer":
      return <Building2 className={cls} aria-hidden="true" />;
    case "owner":
    case "end_user":
      return <Landmark className={cls} aria-hidden="true" />;
    default:
      return <Users className={cls} aria-hidden="true" />;
  }
}

// Color tint for the confidence label dot/border.
function confidenceColor(label: string): string {
  switch (label) {
    case "confirmed":
      return "var(--hot)";
    case "likely":
      return "var(--warm)";
    default:
      return "var(--cold)";
  }
}

export function TeamHierarchy({
  team,
  teamConfidence,
}: {
  team: TeamMember[];
  teamConfidence?: string;
}) {
  const members = [...(team ?? [])].sort((a, b) => {
    const r = roleRank(a.role) - roleRank(b.role);
    if (r !== 0) return r;
    // higher confidence first within the same role
    return (b.confidence ?? 0) - (a.confidence ?? 0);
  });

  if (members.length === 0) {
    return (
      <section className="rounded-lg border border-border bg-surface p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-fg">
            <Users className="h-4 w-4" aria-hidden="true" />
            Project Team
          </h2>
          {teamConfidence ? <TeamConfidenceChip confidence={teamConfidence} /> : null}
        </div>
        <div className="flex flex-col items-center justify-center gap-1 py-6 text-center">
          <Users className="h-6 w-6 text-fg/40" aria-hidden="true" />
          <p className="text-sm font-medium text-fg">Team not yet identified</p>
          <p className="text-xs text-fg/60">
            No general contractor, developer, or owner has been confirmed for this project yet.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-fg">
          <Users className="h-4 w-4" aria-hidden="true" />
          Project Team
        </h2>
        {teamConfidence ? <TeamConfidenceChip confidence={teamConfidence} /> : null}
      </div>

      <ol className="flex flex-col gap-2">
        {members.map((m, i) => (
          <li
            key={`${m.company_id ?? m.company_name}-${m.role}-${i}`}
            className="flex items-start gap-3 rounded-md border border-border bg-bg p-3"
            style={{ borderLeftWidth: 3, borderLeftColor: confidenceColor(m.confidence_label) }}
          >
            <span className="mt-0.5 text-secondary">
              <RoleIcon role={m.role} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-fg/60">
                  {roleText(m.role)}
                </span>
                {m.is_hyperscaler ? (
                  <span
                    className="inline-flex items-center gap-1 rounded-full bg-primary px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary-fg"
                    title="Hyperscaler"
                  >
                    <Cloud className="h-3 w-3" aria-hidden="true" />
                    Hyperscaler
                  </span>
                ) : null}
              </div>
              <p className="truncate text-sm font-medium text-fg" title={m.company_name}>
                {m.company_name}
              </p>
            </div>
            <span
              className="num mt-0.5 inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border px-2 py-0.5 text-[11px] font-medium text-fg"
              title={`Confidence: ${confidenceText(m.confidence_label)}`}
            >
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ backgroundColor: confidenceColor(m.confidence_label) }}
                aria-hidden="true"
              />
              {confidenceText(m.confidence_label)}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

export default TeamHierarchy;
