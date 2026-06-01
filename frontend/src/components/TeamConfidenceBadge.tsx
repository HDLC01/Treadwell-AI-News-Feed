import { HardHat, Building2, User, HelpCircle } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { teamConfidenceLabel } from "../lib/format";
import type { TeamConfidence } from "../lib/types";

interface Props {
  value: TeamConfidence | string | null | undefined;
  className?: string;
}

// The team-confidence rollup is the core signal: a named GC is the strongest
// "the team exists and is reachable" indicator, owner-only the weakest.
const CONFIG: Record<string, { tone: string; Icon: LucideIcon }> = {
  gc_named: {
    tone: "border-primary/50 bg-primary/10 text-primary",
    Icon: HardHat,
  },
  developer_named: {
    tone: "border-secondary/50 bg-secondary/10 text-secondary",
    Icon: Building2,
  },
  owner_only: {
    tone: "border-accent/50 bg-accent/10 text-accent",
    Icon: User,
  },
  unknown: {
    tone: "border-border bg-muted text-cold",
    Icon: HelpCircle,
  },
};

export default function TeamConfidenceBadge({ value, className = "" }: Props) {
  const key = (value as string) || "unknown";
  const cfg = CONFIG[key] ?? CONFIG.unknown;
  const { Icon } = cfg;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${cfg.tone} ${className}`}
      title="Team identification confidence"
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {teamConfidenceLabel(key)}
    </span>
  );
}
