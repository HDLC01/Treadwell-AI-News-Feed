import { MapPin, MapPinOff } from "lucide-react";
import { miles } from "../lib/format";

interface Props {
  distanceMi: number | null | undefined;
  inRadius: boolean | null | undefined;
  className?: string;
}

// Distance from Kansas City + whether the project is inside the service radius
// (350mi for data centers, 70mi otherwise — gate computed server-side).
export default function DistancePill({
  distanceMi,
  inRadius,
  className = "",
}: Props) {
  const inside = inRadius === true;
  const tone = inside
    ? "border-primary/40 bg-primary/10 text-primary"
    : "border-border bg-muted text-cold";
  const Icon = inside ? MapPin : MapPinOff;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${tone} ${className}`}
      title={inside ? "Inside service radius from Kansas City" : "Outside service radius"}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      <span className="num">{miles(distanceMi)}</span>
    </span>
  );
}
