// TypeScript interfaces mirroring SPEC section 4 JSON shapes EXACTLY.
// These key names are the contract — do not rename.

// ---- Controlled vocabularies (mirrors DB CHECK constraints / SPEC enums) ----

export type ProjectType =
  | "data_center"
  | "industrial"
  | "healthcare"
  | "higher_ed"
  | "distribution"
  | "manufacturing"
  | "mission_critical"
  | "other_commercial";

export type Stage =
  | "rumored"
  | "planning"
  | "design"
  | "permitting"
  | "procurement"
  | "pre_bid"
  | "under_construction"
  | "complete"
  | "dead";

export type RelevanceTier = "hot" | "warm" | "cold";

export type TeamConfidence =
  | "gc_named"
  | "developer_named"
  | "owner_only"
  | "unknown";

export type ProjectStatus =
  | "new"
  | "active"
  | "watching"
  | "pursuing"
  | "archived"
  | "dismissed";

export type TeamRole =
  | "general_contractor"
  | "developer"
  | "owner"
  | "end_user"
  | "architect"
  | "engineer"
  | "construction_manager"
  | "utility"
  | "other";

export type CompanyType =
  | "general_contractor"
  | "developer"
  | "owner"
  | "end_user"
  | "architect"
  | "engineer"
  | "construction_manager"
  | "utility"
  | "subcontractor"
  | "unknown";

export type ConfidenceLabel = "confirmed" | "likely" | "rumored";

export type SignalType =
  | "news"
  | "press_release"
  | "permit"
  | "utility_filing"
  | "econ_dev_minutes"
  | "planning_filing"
  | "other";

export type ContactKind = "named_person" | "general_inbox" | "main_line";

export type PipelineRunStatus = "running" | "success" | "partial" | "failed";

// ---- Nested shapes ----

export interface TopTeamMember {
  company_name: string;
  role: TeamRole;
  confidence_label: ConfidenceLabel;
}

export interface TeamMember {
  company_id: string;
  company_name: string;
  company_type: CompanyType;
  role: TeamRole;
  confidence: number;
  confidence_label: ConfidenceLabel;
  is_hyperscaler: boolean;
}

// ---- Core API response shapes (SPEC §4) ----

export interface ProjectSummary {
  id: string;
  title: string;
  project_type: ProjectType;
  stage: Stage | null;
  city: string | null;
  state: string | null;
  county: string | null;
  distance_mi: number | null;
  in_radius: boolean | null;
  within_70mi: boolean | null;
  relevance_score: number | null;
  relevance_tier: RelevanceTier | null;
  team_confidence: TeamConfidence;
  top_team_member: TopTeamMember | null;
  signals_count: number;
  est_megawatts: number | null;
  est_value_usd: number | null;
  est_sqft: number | null;
  status: ProjectStatus;
  last_signal_at: string;
  first_seen_at: string;
}

export interface ProjectDetail extends ProjectSummary {
  summary: string | null;
  address: string | null;
  latitude: number | null;
  longitude: number | null;
  relevance_reasoning: Record<string, unknown> | null;
  team: TeamMember[];
  contacts_count: number;
}

export interface Signal {
  id: string;
  signal_type: SignalType;
  source_name: string | null;
  url: string | null;
  title: string | null;
  published_at: string | null;
  snippet: string | null;
  extraction_confidence: number | null;
}

export interface Contact {
  id: string;
  company_id: string | null;
  company_name: string | null;
  full_name: string | null;
  title: string | null;
  email: string | null;
  phone: string | null;
  contact_kind: ContactKind;
  source: string | null;
  source_url: string | null;
  verified: boolean;
  do_not_contact: boolean;
}

export interface DigestSummary {
  digest_date: string;
  new_count: number;
  updated_count: number;
  project_count: number;
}

export interface DigestDetail {
  digest_date: string;
  html_body: string | null;
  project_ids: string[];
  new_count: number;
  updated_count: number;
}

export interface PipelineRun {
  id: string;
  started_at: string;
  finished_at: string | null;
  status: PipelineRunStatus;
  trigger: string;
  sources_fetched: number;
  signals_ingested: number;
  projects_created: number;
  projects_updated: number;
  errors: unknown[];
}

export interface Stats {
  total: number;
  new: number;
  today: number;
  hot: number;
  in_radius: number;
  within_70mi: number;
  data_centers: number;
}

// ---- Paginated list envelope (GET /api/projects) ----

export interface Paginated<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

// ---- Query params for the project feed ----

export type ProjectSort = "relevance" | "distance" | "recent";

export interface ProjectQuery {
  q?: string;
  project_type?: string; // csv
  stage?: string; // csv
  in_radius?: boolean;
  tier?: string; // csv of hot/warm/cold
  team_confidence?: string; // csv
  status?: string; // csv
  sort?: ProjectSort;
  page?: number;
  page_size?: number;
}
