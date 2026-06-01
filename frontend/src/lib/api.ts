// Typed fetch wrappers for the FastAPI backend (SPEC §5).
// Base URL is "" — same origin in production (FastAPI serves the SPA),
// proxied to :8890 by Vite in dev.

import type {
  Contact,
  DigestDetail,
  DigestSummary,
  Paginated,
  PipelineRun,
  ProjectDetail,
  ProjectQuery,
  ProjectStatus,
  ProjectSummary,
  Signal,
  Stats,
} from "./types";

const BASE = "";

/** Error carrying the HTTP status so callers (e.g. contacts gate) can branch on 401. */
export class ApiError extends Error {
  status: number;
  body: string;
  constructor(status: number, message: string, body = "") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function request<T>(
  path: string,
  init?: RequestInit & { rawText?: boolean },
): Promise<T> {
  const { rawText, headers, ...rest } = init ?? {};

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...rest,
      headers: {
        Accept: "application/json",
        ...(rest.body ? { "Content-Type": "application/json" } : {}),
        ...(headers ?? {}),
      },
    });
  } catch (e) {
    throw new ApiError(0, `Network error: ${(e as Error).message}`);
  }

  if (!res.ok) {
    let body = "";
    try {
      body = await res.text();
    } catch {
      // ignore body read failure
    }
    throw new ApiError(res.status, `${res.status} ${res.statusText}`, body);
  }

  if (rawText) {
    return (await res.text()) as unknown as T;
  }

  // Tolerate empty 204-style bodies.
  const text = await res.text();
  if (!text) return undefined as unknown as T;
  return JSON.parse(text) as T;
}

function buildQuery(params: ProjectQuery): string {
  const sp = new URLSearchParams();
  if (params.q) sp.set("q", params.q);
  if (params.project_type) sp.set("project_type", params.project_type);
  if (params.stage) sp.set("stage", params.stage);
  if (params.in_radius !== undefined) sp.set("in_radius", String(params.in_radius));
  if (params.tier) sp.set("tier", params.tier);
  if (params.team_confidence) sp.set("team_confidence", params.team_confidence);
  if (params.status) sp.set("status", params.status);
  if (params.sort) sp.set("sort", params.sort);
  if (params.page) sp.set("page", String(params.page));
  if (params.page_size) sp.set("page_size", String(params.page_size));
  const qs = sp.toString();
  return qs ? `?${qs}` : "";
}

// ---- Projects ----

export function getProjects(
  params: ProjectQuery = {},
): Promise<Paginated<ProjectSummary>> {
  return request<Paginated<ProjectSummary>>(`/api/projects${buildQuery(params)}`);
}

export function getProject(id: string): Promise<ProjectDetail> {
  return request<ProjectDetail>(`/api/projects/${encodeURIComponent(id)}`);
}

export function getProjectSignals(id: string): Promise<Signal[]> {
  return request<Signal[]>(`/api/projects/${encodeURIComponent(id)}/signals`);
}

export function getProjectContacts(
  id: string,
  key?: string,
): Promise<Contact[]> {
  return request<Contact[]>(`/api/projects/${encodeURIComponent(id)}/contacts`, {
    headers: key ? { "X-Contacts-Key": key } : {},
  });
}

export function patchProjectStatus(
  id: string,
  status: ProjectStatus,
): Promise<ProjectSummary> {
  return request<ProjectSummary>(`/api/projects/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export function mergeProject(
  id: string,
  targetId: string,
): Promise<{ ok: boolean; merged_into: string }> {
  return request<{ ok: boolean; merged_into: string }>(
    `/api/projects/${encodeURIComponent(id)}/merge`,
    {
      method: "POST",
      body: JSON.stringify({ target_id: targetId }),
    },
  );
}

export function getStats(): Promise<Stats> {
  return request<Stats>("/api/stats");
}

// ---- Digests ----

export function getDigests(): Promise<DigestSummary[]> {
  return request<DigestSummary[]>("/api/digests");
}

export function getDigest(date: string): Promise<DigestDetail> {
  return request<DigestDetail>(`/api/digests/${encodeURIComponent(date)}`);
}

// ---- Admin ----

export function getRuns(): Promise<PipelineRun[]> {
  return request<PipelineRun[]>("/api/admin/runs");
}

export function runPipeline(): Promise<{
  ok: boolean;
  started: boolean;
  note: string;
}> {
  return request<{ ok: boolean; started: boolean; note: string }>(
    "/api/admin/run-pipeline",
    { method: "POST" },
  );
}

// ---- Subscribers ----

export function subscribe(
  email: string,
  name?: string,
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/subscribers", {
    method: "POST",
    body: JSON.stringify({ email, full_name: name ?? undefined }),
  });
}
