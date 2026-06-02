// Formatting helpers + human-readable label maps.
// Numerals/distances/MW/$ render via the `.num` class (Fira Code, tabular-nums).

import type {
  ProjectType,
  Stage,
  TeamRole,
  TeamConfidence,
  RelevanceTier,
  CompanyType,
  ConfidenceLabel,
  SignalType,
  ProjectStatus,
  ContactKind,
} from "./types";

const EMPTY = "—";

// Treadwell's home timezone (US Central). Every human-facing calendar date is
// pinned to Central so all viewers — including UTC+8 — see the same day Kyle
// does, not their own local day. Internal elapsed-time math (ms diffs) is
// timezone-agnostic and needs no pinning.
const CENTRAL_TZ = "America/Chicago";

/** A date's YYYY-MM-DD on the US Central calendar. */
export function centralYMD(d: Date): string {
  // en-CA renders ISO-style YYYY-MM-DD.
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: CENTRAL_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

/** Whole-day difference (a − b) measured on the US Central calendar. */
export function centralDayDiff(a: Date, b: Date): number {
  const [ay, am, ad] = centralYMD(a).split("-").map(Number);
  const [by, bm, bd] = centralYMD(b).split("-").map(Number);
  return Math.round(
    (Date.UTC(ay, am - 1, ad) - Date.UTC(by, bm - 1, bd)) / 86_400_000,
  );
}

/** Great-circle distance in miles, e.g. "47 mi" / "312 mi". */
export function miles(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return EMPTY;
  const rounded = Math.round(n);
  return `${rounded.toLocaleString("en-US")} mi`;
}

/** Compact USD, e.g. "$1.2B", "$450M", "$2.5K". */
export function money(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return EMPTY;
  const abs = Math.abs(n);
  if (abs >= 1_000_000_000) return `$${trimZero(n / 1_000_000_000)}B`;
  if (abs >= 1_000_000) return `$${trimZero(n / 1_000_000)}M`;
  if (abs >= 1_000) return `$${trimZero(n / 1_000)}K`;
  return `$${Math.round(n).toLocaleString("en-US")}`;
}

/** Megawatts, e.g. "250 MW", "37.5 MW". */
export function megawatts(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return EMPTY;
  return `${trimZero(n)} MW`;
}

/** Square footage, compact: "1.2M sq ft", "450K sq ft", "900 sq ft". */
export function sqft(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return EMPTY;
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `${trimZero(n / 1_000_000)}M sq ft`;
  if (abs >= 1_000) return `${trimZero(n / 1_000)}K sq ft`;
  return `${Math.round(n).toLocaleString("en-US")} sq ft`;
}

/** Relative date for signal recency, e.g. "today", "3d ago", "Apr 12". */
export function relativeDate(iso: string | null | undefined): string {
  if (!iso) return EMPTY;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return EMPTY;
  const now = Date.now();
  const diffMs = now - then.getTime();
  const diffMin = Math.round(diffMs / 60_000);
  const diffHr = Math.round(diffMs / 3_600_000);
  const diffDay = Math.round(diffMs / 86_400_000);

  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay < 1) return "today";
  if (diffDay === 1) return "yesterday";
  if (diffDay < 7) return `${diffDay}d ago`;
  if (diffDay < 30) return `${Math.round(diffDay / 7)}w ago`;

  // Older than a month: absolute date, pinned to US Central (Kyle's day).
  const sameYear =
    centralYMD(then).slice(0, 4) === centralYMD(new Date()).slice(0, 4);
  return then.toLocaleDateString("en-US", {
    timeZone: CENTRAL_TZ,
    month: "short",
    day: "numeric",
    year: sameYear ? undefined : "numeric",
  });
}

/** Full absolute date, e.g. "Apr 12, 2026". */
export function absoluteDate(iso: string | null | undefined): string {
  if (!iso) return EMPTY;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return EMPTY;
  return d.toLocaleDateString("en-US", {
    timeZone: CENTRAL_TZ,
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/** Score out of 100, e.g. "87". */
export function score(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return EMPTY;
  return `${Math.round(n)}`;
}

function trimZero(n: number): string {
  // One decimal place, but strip a trailing ".0".
  const s = n.toFixed(1);
  return s.endsWith(".0") ? s.slice(0, -2) : s;
}

// ---- Human-readable label maps ----

export const PROJECT_TYPE_LABELS: Record<ProjectType, string> = {
  data_center: "Data Center",
  industrial: "Industrial",
  healthcare: "Healthcare",
  higher_ed: "Higher Ed",
  distribution: "Distribution",
  manufacturing: "Manufacturing",
  mission_critical: "Mission Critical",
  other_commercial: "Other Commercial",
};

export const STAGE_LABELS: Record<Stage, string> = {
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

export const ROLE_LABELS: Record<TeamRole, string> = {
  general_contractor: "General Contractor",
  developer: "Developer",
  owner: "Owner",
  end_user: "End User",
  architect: "Architect",
  engineer: "Engineer",
  construction_manager: "Construction Manager",
  utility: "Utility",
  other: "Other",
};

export const COMPANY_TYPE_LABELS: Record<CompanyType, string> = {
  general_contractor: "General Contractor",
  developer: "Developer",
  owner: "Owner",
  end_user: "End User",
  architect: "Architect",
  engineer: "Engineer",
  construction_manager: "Construction Manager",
  utility: "Utility",
  subcontractor: "Subcontractor",
  unknown: "Unknown",
};

export const TEAM_CONFIDENCE_LABELS: Record<TeamConfidence, string> = {
  gc_named: "GC Named",
  developer_named: "Developer Named",
  owner_only: "Owner Only",
  unknown: "Team Unknown",
};

export const TIER_LABELS: Record<RelevanceTier, string> = {
  hot: "Hot",
  warm: "Warm",
  cold: "Cold",
};

export const CONFIDENCE_LABEL_LABELS: Record<ConfidenceLabel, string> = {
  confirmed: "Confirmed",
  likely: "Likely",
  rumored: "Rumored",
};

export const SIGNAL_TYPE_LABELS: Record<SignalType, string> = {
  news: "News",
  press_release: "Press Release",
  permit: "Permit",
  utility_filing: "Utility Filing",
  econ_dev_minutes: "Econ-Dev Minutes",
  planning_filing: "Planning Filing",
  other: "Other",
};

export const STATUS_LABELS: Record<ProjectStatus, string> = {
  new: "New",
  active: "Active",
  watching: "Watching",
  pursuing: "Pursuing",
  won: "Won",
  passed: "Passed",
  archived: "Archived",
  dismissed: "Dismissed",
};

export const CONTACT_KIND_LABELS: Record<ContactKind, string> = {
  named_person: "Named Person",
  general_inbox: "General Inbox",
  main_line: "Main Line",
};

// Safe label lookups that tolerate unknown / off-list values from the API.
export function projectTypeLabel(t: string | null | undefined): string {
  if (!t) return EMPTY;
  return PROJECT_TYPE_LABELS[t as ProjectType] ?? titleCase(t);
}

export function stageLabel(s: string | null | undefined): string {
  if (!s) return EMPTY;
  return STAGE_LABELS[s as Stage] ?? titleCase(s);
}

export function roleLabel(r: string | null | undefined): string {
  if (!r) return EMPTY;
  return ROLE_LABELS[r as TeamRole] ?? titleCase(r);
}

export function companyTypeLabel(c: string | null | undefined): string {
  if (!c) return EMPTY;
  return COMPANY_TYPE_LABELS[c as CompanyType] ?? titleCase(c);
}

export function teamConfidenceLabel(t: string | null | undefined): string {
  if (!t) return TEAM_CONFIDENCE_LABELS.unknown;
  return TEAM_CONFIDENCE_LABELS[t as TeamConfidence] ?? titleCase(t);
}

export function tierLabel(t: string | null | undefined): string {
  if (!t) return EMPTY;
  return TIER_LABELS[t as RelevanceTier] ?? titleCase(t);
}

export function confidenceLabelText(c: string | null | undefined): string {
  if (!c) return EMPTY;
  return CONFIDENCE_LABEL_LABELS[c as ConfidenceLabel] ?? titleCase(c);
}

export function signalTypeLabel(s: string | null | undefined): string {
  if (!s) return EMPTY;
  return SIGNAL_TYPE_LABELS[s as SignalType] ?? titleCase(s);
}

export function statusLabel(s: string | null | undefined): string {
  if (!s) return EMPTY;
  return STATUS_LABELS[s as ProjectStatus] ?? titleCase(s);
}

export function contactKindLabel(c: string | null | undefined): string {
  if (!c) return EMPTY;
  return CONTACT_KIND_LABELS[c as ContactKind] ?? titleCase(c);
}

/** Location line, e.g. "Olathe, KS" / "St. Louis, MO" / "—". */
export function locationLine(
  city: string | null | undefined,
  state: string | null | undefined,
  county?: string | null | undefined,
): string {
  const parts = [city, state].filter(Boolean) as string[];
  if (parts.length === 0) {
    return county ? `${county} County` : EMPTY;
  }
  return parts.join(", ");
}

function titleCase(s: string): string {
  return s
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
