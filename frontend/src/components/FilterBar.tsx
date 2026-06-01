import { useEffect, useRef, useState } from "react";
import {
  Search,
  X,
  SlidersHorizontal,
  ArrowUpDown,
  MapPin,
  Check,
} from "lucide-react";
import type {
  ProjectSort,
  ProjectType,
  Stage,
  RelevanceTier,
  TeamConfidence,
} from "../lib/types";
import {
  PROJECT_TYPE_LABELS,
  STAGE_LABELS,
  TIER_LABELS,
  TEAM_CONFIDENCE_LABELS,
} from "../lib/format";

// The shape FeedPage owns. csv string fields hold comma-separated enum values.
export interface FilterState {
  q: string;
  project_type: string[];
  stage: string[];
  tier: string[];
  team_confidence: string[];
  in_radius: boolean | null; // null = any, true = inside only
  sort: ProjectSort;
}

interface Props {
  value: FilterState;
  onChange: (next: FilterState) => void;
  resultCount?: number | null;
}

const TYPE_OPTIONS = Object.entries(PROJECT_TYPE_LABELS) as [
  ProjectType,
  string,
][];
const STAGE_OPTIONS = Object.entries(STAGE_LABELS) as [Stage, string][];
const TIER_OPTIONS = Object.entries(TIER_LABELS) as [RelevanceTier, string][];
const TEAM_OPTIONS = Object.entries(TEAM_CONFIDENCE_LABELS) as [
  TeamConfidence,
  string,
][];

const SORT_OPTIONS: { value: ProjectSort; label: string }[] = [
  { value: "relevance", label: "Relevance" },
  { value: "distance", label: "Distance" },
  { value: "recent", label: "Most recent" },
];

export default function FilterBar({ value, onChange, resultCount }: Props) {
  const [searchText, setSearchText] = useState(value.q);
  const [expanded, setExpanded] = useState(false);
  const debounceRef = useRef<number | undefined>(undefined);

  // Keep local search box in sync if the parent resets filters.
  useEffect(() => {
    setSearchText(value.q);
  }, [value.q]);

  // Debounce search so we don't refetch on every keystroke.
  useEffect(() => {
    if (searchText === value.q) return;
    window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      onChange({ ...value, q: searchText });
    }, 300);
    return () => window.clearTimeout(debounceRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchText]);

  const toggleIn = (key: keyof FilterState, v: string) => {
    const arr = value[key] as string[];
    const next = arr.includes(v)
      ? arr.filter((x) => x !== v)
      : [...arr, v];
    onChange({ ...value, [key]: next });
  };

  const setRadius = (next: boolean | null) => {
    onChange({ ...value, in_radius: next });
  };

  const activeChips =
    value.project_type.length +
    value.stage.length +
    value.tier.length +
    value.team_confidence.length +
    (value.in_radius === true ? 1 : 0);

  const clearAll = () => {
    setSearchText("");
    onChange({
      q: "",
      project_type: [],
      stage: [],
      tier: [],
      team_confidence: [],
      in_radius: null,
      sort: value.sort,
    });
  };

  return (
    <div className="rounded-xl border border-border bg-surface p-3 sm:p-4">
      {/* Row 1: search + radius toggle + sort + filters button */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-cold"
            aria-hidden="true"
          />
          <input
            type="search"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="Search projects, cities, companies…"
            aria-label="Search projects"
            className="h-11 w-full rounded-lg border border-border bg-bg pl-9 pr-9 text-sm text-fg placeholder:text-cold focus:border-primary focus:outline-none"
          />
          {searchText && (
            <button
              type="button"
              onClick={() => setSearchText("")}
              aria-label="Clear search"
              className="absolute right-2 top-1/2 inline-flex h-7 w-7 -translate-y-1/2 cursor-pointer items-center justify-center rounded-md text-cold transition-colors duration-200 hover:bg-muted"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        </div>

        {/* In-radius toggle */}
        <button
          type="button"
          onClick={() => setRadius(value.in_radius === true ? null : true)}
          aria-pressed={value.in_radius === true}
          className={[
            "inline-flex h-11 cursor-pointer items-center justify-center gap-1.5 rounded-lg border px-3 text-sm font-medium transition-colors duration-200",
            value.in_radius === true
              ? "border-primary bg-primary text-primary-fg"
              : "border-border bg-bg text-fg hover:bg-muted",
          ].join(" ")}
          title="Show only projects inside the Kansas City service radius"
        >
          <MapPin className="h-4 w-4" aria-hidden="true" />
          In radius
        </button>

        {/* Sort */}
        <label className="relative inline-flex h-11 items-center">
          <ArrowUpDown
            className="pointer-events-none absolute left-3 h-4 w-4 text-cold"
            aria-hidden="true"
          />
          <span className="sr-only">Sort projects</span>
          <select
            value={value.sort}
            onChange={(e) =>
              onChange({ ...value, sort: e.target.value as ProjectSort })
            }
            className="h-11 cursor-pointer appearance-none rounded-lg border border-border bg-bg pl-9 pr-8 text-sm text-fg focus:border-primary focus:outline-none"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>

        {/* Filters expander */}
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          aria-expanded={expanded}
          className={[
            "inline-flex h-11 cursor-pointer items-center justify-center gap-1.5 rounded-lg border px-3 text-sm font-medium transition-colors duration-200",
            expanded || activeChips > 0
              ? "border-primary text-primary"
              : "border-border text-fg hover:bg-muted",
          ].join(" ")}
        >
          <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
          Filters
          {activeChips > 0 && (
            <span className="num inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1 text-xs font-semibold text-primary-fg">
              {activeChips}
            </span>
          )}
        </button>
      </div>

      {/* Row 2: chip groups (collapsible) */}
      {expanded && (
        <div className="mt-3 space-y-3 border-t border-border pt-3">
          <ChipGroup
            label="Project type"
            options={TYPE_OPTIONS}
            selected={value.project_type}
            onToggle={(v) => toggleIn("project_type", v)}
          />
          <ChipGroup
            label="Stage"
            options={STAGE_OPTIONS}
            selected={value.stage}
            onToggle={(v) => toggleIn("stage", v)}
          />
          <ChipGroup
            label="Relevance"
            options={TIER_OPTIONS}
            selected={value.tier}
            onToggle={(v) => toggleIn("tier", v)}
          />
          <ChipGroup
            label="Team confidence"
            options={TEAM_OPTIONS}
            selected={value.team_confidence}
            onToggle={(v) => toggleIn("team_confidence", v)}
          />
        </div>
      )}

      {/* Row 3: active summary + clear */}
      {(activeChips > 0 || value.q) && (
        <div className="mt-3 flex items-center justify-between gap-2 border-t border-border pt-2">
          <span className="text-xs text-cold">
            {resultCount !== null && resultCount !== undefined ? (
              <>
                <span className="num font-medium text-fg">
                  {resultCount.toLocaleString("en-US")}
                </span>{" "}
                {resultCount === 1 ? "project" : "projects"}
              </>
            ) : (
              "Filtered"
            )}
          </span>
          <button
            type="button"
            onClick={clearAll}
            className="inline-flex cursor-pointer items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-primary transition-colors duration-200 hover:bg-muted"
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
            Clear all
          </button>
        </div>
      )}
    </div>
  );
}

function ChipGroup({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: [string, string][];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-cold">
        {label}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {options.map(([val, lbl]) => {
          const on = selected.includes(val);
          return (
            <button
              key={val}
              type="button"
              onClick={() => onToggle(val)}
              aria-pressed={on}
              className={[
                "inline-flex cursor-pointer items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors duration-200",
                on
                  ? "border-primary bg-primary text-primary-fg"
                  : "border-border bg-bg text-fg hover:bg-muted",
              ].join(" ")}
            >
              {on && <Check className="h-3 w-3" aria-hidden="true" />}
              {lbl}
            </button>
          );
        })}
      </div>
    </div>
  );
}
