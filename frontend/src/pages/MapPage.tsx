import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Circle,
  Popup,
} from "react-leaflet";
import { AlertCircle, MapPin } from "lucide-react";
import "leaflet/dist/leaflet.css";
import EmptyState from "../components/EmptyState";
import { getConfig, getMapPoints, ApiError } from "../lib/api";
import type { MapPoint, RadarConfig, RelevanceTier } from "../lib/types";
import { miles, projectTypeLabel, locationLine } from "../lib/format";

// Status colors map to the design-system tokens (resolved to hex so Leaflet's
// SVG vector layers, which render outside the Tailwind class tree, paint
// correctly in both themes). null tier renders as cold.
const TIER_COLORS: Record<RelevanceTier, string> = {
  hot: "#DC2626",
  warm: "#D97706",
  cold: "#64748B",
};

const PRIMARY = "#1E40AF";
const MILES_TO_METERS = 1609.34;

function tierColor(tier: RelevanceTier | null): string {
  return TIER_COLORS[tier ?? "cold"];
}

function tierLabel(tier: RelevanceTier | null): string {
  const t = tier ?? "cold";
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export default function MapPage() {
  const [config, setConfig] = useState<RadarConfig | null>(null);
  const [points, setPoints] = useState<MapPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([getConfig(), getMapPoints()])
      .then(([cfg, pts]) => {
        if (cancelled) return;
        setConfig(cfg);
        setPoints(Array.isArray(pts) ? pts : []);
      })
      .catch((e) => {
        if (cancelled) return;
        const msg =
          e instanceof ApiError
            ? `Could not load the map (${e.status || "network"}).`
            : "Could not load the map.";
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const center = useMemo<[number, number] | null>(
    () => (config ? [config.kc_lat, config.kc_lon] : null),
    [config],
  );

  // Tier filter: which categories are shown on the map (all on by default).
  const [tiers, setTiers] = useState<Set<RelevanceTier>>(
    () => new Set<RelevanceTier>(["hot", "warm", "cold"]),
  );
  const counts = useMemo(() => {
    const c: Record<RelevanceTier, number> = { hot: 0, warm: 0, cold: 0 };
    for (const p of points) c[p.relevance_tier ?? "cold"] += 1;
    return c;
  }, [points]);
  const visiblePoints = useMemo(
    () => points.filter((p) => tiers.has(p.relevance_tier ?? "cold")),
    [points, tiers],
  );
  const toggleTier = (t: RelevanceTier) =>
    setTiers((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-bold tracking-tight text-fg sm:text-2xl">
          <MapPin className="h-5 w-5 text-primary" aria-hidden="true" />
          Radar Map
        </h1>
        <p className="mt-1 text-sm text-cold">
          Treadwell&rsquo;s office at center, the service radius drawn around it,
          and every located project plotted by relevance.
        </p>
      </div>

      {/* Tier filter — show leads by category (Hot / Warm / Cold) */}
      {!loading && !error && center && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-cold">Show:</span>
          {(["hot", "warm", "cold"] as const).map((t) => {
            const on = tiers.has(t);
            return (
              <button
                key={t}
                type="button"
                onClick={() => toggleTier(t)}
                aria-pressed={on}
                className="inline-flex min-h-[44px] cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold transition-all duration-150 sm:min-h-0"
                style={{
                  borderColor: TIER_COLORS[t],
                  color: TIER_COLORS[t],
                  backgroundColor: on ? `${TIER_COLORS[t]}1A` : "transparent",
                  textDecoration: on ? "none" : "line-through",
                }}
                title={on ? `Hide ${tierLabel(t)}` : `Show ${tierLabel(t)}`}
              >
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ backgroundColor: TIER_COLORS[t] }}
                  aria-hidden="true"
                />
                {tierLabel(t)}
                <span className="num">{counts[t]}</span>
              </button>
            );
          })}
          <span className="text-xs text-cold">
            {visiblePoints.length} of {points.length} shown
          </span>
        </div>
      )}

      {loading ? (
        <div className="h-[calc(100vh-8rem)] w-full animate-pulse rounded-xl border border-border bg-muted motion-reduce:animate-none" />
      ) : error ? (
        <EmptyState
          title="Something went wrong"
          message={`${error} Make sure the backend is running on port 8890, then try again.`}
          icon={AlertCircle}
        />
      ) : !center ? (
        <EmptyState
          title="Map unavailable"
          message="The office location has not been configured yet."
          icon={AlertCircle}
        />
      ) : points.length === 0 ? (
        <EmptyState
          title="No located projects yet"
          message="Projects appear here once they have coordinates. The office and service radius are still shown on the map below."
          icon={MapPin}
        />
      ) : null}

      {/* The map renders whenever we have an office anchor, even with zero
          points — the office + radius ring are still useful on their own. */}
      {!loading && !error && center && (
        <div className="relative h-[calc(100vh-8rem)] w-full overflow-hidden rounded-xl border border-border">
          <MapContainer
            center={center}
            zoom={9}
            scrollWheelZoom
            className="h-full w-full"
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            {/* Wider data-center radius (lighter) drawn first so the tighter
                "other" radius layers on top. */}
            {config && config.data_center_radius_mi > 0 && (
              <Circle
                center={center}
                radius={config.data_center_radius_mi * MILES_TO_METERS}
                pathOptions={{
                  color: PRIMARY,
                  weight: 1,
                  opacity: 0.35,
                  fillColor: PRIMARY,
                  fillOpacity: 0.04,
                }}
              />
            )}

            {config && config.other_radius_mi > 0 && (
              <Circle
                center={center}
                radius={config.other_radius_mi * MILES_TO_METERS}
                pathOptions={{
                  color: PRIMARY,
                  weight: 1.5,
                  opacity: 0.5,
                  fillColor: PRIMARY,
                  fillOpacity: 0.07,
                }}
              />
            )}

            {/* Office anchor */}
            <CircleMarker
              center={center}
              radius={7}
              pathOptions={{
                color: "#ffffff",
                weight: 2,
                fillColor: PRIMARY,
                fillOpacity: 1,
              }}
            >
              <Popup>
                <span className="font-semibold">Treadwell office</span>
              </Popup>
            </CircleMarker>

            {/* Projects (filtered by the active tier toggles) */}
            {visiblePoints.map((p) => {
              const color = tierColor(p.relevance_tier);
              const loc = locationLine(p.city, p.state);
              return (
                <CircleMarker
                  key={p.id}
                  center={[p.latitude, p.longitude]}
                  radius={6}
                  pathOptions={{
                    color: "#ffffff",
                    weight: 1.5,
                    fillColor: color,
                    fillOpacity: 0.9,
                  }}
                >
                  <Popup>
                    <div className="min-w-[10rem] space-y-1">
                      <div className="text-sm font-semibold leading-snug">
                        {p.title}
                      </div>
                      <div className="text-xs text-slate-600">
                        {projectTypeLabel(p.project_type)}
                        {loc !== "—" ? ` · ${loc}` : ""}
                      </div>
                      <div className="flex items-center gap-1.5 text-xs">
                        <span
                          className="inline-block h-2 w-2 shrink-0 rounded-full"
                          style={{ backgroundColor: color }}
                          aria-hidden="true"
                        />
                        <span>{tierLabel(p.relevance_tier)}</span>
                        <span className="text-slate-500">·</span>
                        <span>{miles(p.distance_mi)}</span>
                      </div>
                      <div className="text-xs">
                        {p.within_70mi === true ? (
                          <span className="font-medium text-blue-700">
                            Within 70 mi
                          </span>
                        ) : p.within_70mi === false ? (
                          <span className="text-slate-500">Outside 70 mi</span>
                        ) : null}
                      </div>
                      <Link
                        to={`/project/${p.id}`}
                        className="inline-flex min-h-[44px] items-center text-xs font-semibold text-blue-700 underline"
                      >
                        View project
                      </Link>
                    </div>
                  </Popup>
                </CircleMarker>
              );
            })}
          </MapContainer>

          {/* Legend overlay (above Leaflet panes; z-[1000] clears tile/marker panes). */}
          <div className="pointer-events-none absolute bottom-3 left-3 z-[1000] rounded-lg border border-border bg-surface/95 px-3 py-2 text-xs shadow-md backdrop-blur">
            <div className="mb-1 font-semibold text-fg">Relevance</div>
            <ul className="space-y-1">
              {(["hot", "warm", "cold"] as const).map((t) => (
                <li key={t} className="flex items-center gap-1.5 text-fg/80">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: TIER_COLORS[t] }}
                    aria-hidden="true"
                  />
                  {tierLabel(t)}
                </li>
              ))}
              <li className="flex items-center gap-1.5 text-fg/80">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full border border-white"
                  style={{ backgroundColor: PRIMARY }}
                  aria-hidden="true"
                />
                Office
              </li>
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
