import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AlertCircle } from "lucide-react";
import FilterBar, { type FilterState } from "../components/FilterBar";
import ProjectCard from "../components/ProjectCard";
import Pagination from "../components/Pagination";
import EmptyState from "../components/EmptyState";
import { ProjectGridSkeleton } from "../components/Skeleton";
import { getProjects, getStats, ApiError } from "../lib/api";
import type {
  Paginated,
  ProjectSummary,
  ProjectSort,
  Stats,
} from "../lib/types";

const PAGE_SIZE = 25;
const VALID_SORTS: ProjectSort[] = ["relevance", "distance", "recent"];

function csvToArr(v: string | null): string[] {
  if (!v) return [];
  return v
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function filtersFromParams(sp: URLSearchParams): FilterState {
  const sortRaw = sp.get("sort") as ProjectSort | null;
  const inRadiusRaw = sp.get("in_radius");
  return {
    q: sp.get("q") ?? "",
    project_type: csvToArr(sp.get("project_type")),
    stage: csvToArr(sp.get("stage")),
    tier: csvToArr(sp.get("tier")),
    team_confidence: csvToArr(sp.get("team_confidence")),
    in_radius: inRadiusRaw === "true" ? true : null,
    sort: sortRaw && VALID_SORTS.includes(sortRaw) ? sortRaw : "relevance",
  };
}

function paramsFromFilters(f: FilterState, page: number): URLSearchParams {
  const sp = new URLSearchParams();
  if (f.q) sp.set("q", f.q);
  if (f.project_type.length) sp.set("project_type", f.project_type.join(","));
  if (f.stage.length) sp.set("stage", f.stage.join(","));
  if (f.tier.length) sp.set("tier", f.tier.join(","));
  if (f.team_confidence.length)
    sp.set("team_confidence", f.team_confidence.join(","));
  if (f.in_radius === true) sp.set("in_radius", "true");
  if (f.sort !== "relevance") sp.set("sort", f.sort);
  if (page > 1) sp.set("page", String(page));
  return sp;
}

export default function FeedPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const filters = useMemo(
    () => filtersFromParams(searchParams),
    [searchParams],
  );
  const page = useMemo(() => {
    const p = parseInt(searchParams.get("page") ?? "1", 10);
    return Number.isFinite(p) && p > 0 ? p : 1;
  }, [searchParams]);

  const [stats, setStats] = useState<Stats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [data, setData] = useState<Paginated<ProjectSummary> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Stats load once on mount.
  useEffect(() => {
    let cancelled = false;
    setStatsLoading(true);
    getStats()
      .then((s) => {
        if (!cancelled) setStats(s);
      })
      .catch(() => {
        // Stats are non-critical; leave them blank on failure.
        if (!cancelled) setStats(null);
      })
      .finally(() => {
        if (!cancelled) setStatsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Projects refetch whenever filters or page change.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getProjects({
      q: filters.q || undefined,
      project_type: filters.project_type.join(",") || undefined,
      stage: filters.stage.join(",") || undefined,
      tier: filters.tier.join(",") || undefined,
      team_confidence: filters.team_confidence.join(",") || undefined,
      in_radius: filters.in_radius === true ? true : undefined,
      sort: filters.sort,
      page,
      page_size: PAGE_SIZE,
    })
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e) => {
        if (!cancelled) {
          const msg =
            e instanceof ApiError
              ? `Could not load projects (${e.status || "network"}).`
              : "Could not load projects.";
          setError(msg);
          setData(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filters, page]);

  const handleFilterChange = useCallback(
    (next: FilterState) => {
      // Any filter change resets to page 1.
      setSearchParams(paramsFromFilters(next, 1), { replace: false });
    },
    [setSearchParams],
  );

  const handlePageChange = useCallback(
    (nextPage: number) => {
      setSearchParams(paramsFromFilters(filters, nextPage), { replace: false });
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
    [filters, setSearchParams],
  );

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = data?.total_pages ?? 1;

  return (
    <div className="space-y-5">
      {/* Stats strip — one slim bar (replaces six boxed stat cards) */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 rounded-xl border border-border bg-surface px-4 py-2.5">
        <Stat value={stats?.total} label="tracked" loading={statsLoading} />
        <span className="hidden h-4 w-px bg-border sm:inline-block" aria-hidden="true" />
        <Stat value={stats?.hot} label="hot" tone="hot" loading={statsLoading} />
        <Stat
          value={stats?.data_centers}
          label="data centers"
          tone="primary"
          loading={statsLoading}
        />
        <Stat
          value={stats?.within_70mi}
          label="within 70 mi"
          tone="primary"
          loading={statsLoading}
        />
        <span className="hidden h-4 w-px bg-border sm:inline-block" aria-hidden="true" />
        <Stat value={stats?.new} label="new" loading={statsLoading} />
        <Stat value={stats?.today} label="today" loading={statsLoading} />
      </div>

      {/* Filters */}
      <FilterBar
        value={filters}
        onChange={handleFilterChange}
        resultCount={data ? total : null}
      />

      {/* Results */}
      {loading ? (
        <ProjectGridSkeleton count={6} />
      ) : error ? (
        <EmptyState
          title="Something went wrong"
          message={`${error} Make sure the backend is running on port 8890, then try again.`}
          icon={AlertCircle}
        />
      ) : items.length === 0 ? (
        <EmptyState
          title="No projects match these filters"
          message="Try clearing a filter or widening the radius. In demo mode, sample projects load automatically with no filters set."
        />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {items.map((p) => (
              <ProjectCard key={p.id} project={p} />
            ))}
          </div>
          <Pagination
            page={data?.page ?? page}
            totalPages={totalPages}
            total={total}
            pageSize={data?.page_size ?? PAGE_SIZE}
            onPageChange={handlePageChange}
          />
        </>
      )}
    </div>
  );
}

// One inline KPI in the slim stats strip: bold number + muted label.
function Stat({
  value,
  label,
  tone,
  loading,
}: {
  value?: number;
  label: string;
  tone?: "hot" | "primary";
  loading?: boolean;
}) {
  const toneCls =
    tone === "hot" ? "text-hot" : tone === "primary" ? "text-primary" : "text-fg";
  return (
    <span className="inline-flex items-baseline gap-1.5">
      {loading ? (
        <span className="inline-block h-4 w-6 animate-pulse rounded bg-muted motion-reduce:animate-none" />
      ) : (
        <span className={`num text-base font-semibold leading-none ${toneCls}`}>
          {(value ?? 0).toLocaleString("en-US")}
        </span>
      )}
      <span className="text-xs text-cold">{label}</span>
    </span>
  );
}
