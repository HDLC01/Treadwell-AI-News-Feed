import { stageLabel } from "../lib/format";
import type { Stage } from "../lib/types";

interface Props {
  stage: Stage | string | null | undefined;
  className?: string;
}

// Map each stage to a subtle tone. Earlier stages = warmer (more opportunity to
// get in front of the team); later stages cool off.
const STAGE_TONE: Record<string, string> = {
  rumored: "border-cold/40 text-cold",
  planning: "border-secondary/50 text-info-text",
  design: "border-secondary/50 text-info-text",
  permitting: "border-accent/50 text-warm-text",
  procurement: "border-accent/50 text-warm-text",
  pre_bid: "border-hot/50 text-hot",
  under_construction: "border-cold/40 text-cold",
  complete: "border-cold/30 text-cold",
  dead: "border-cold/30 text-cold line-through",
};

export default function StageBadge({ stage, className = "" }: Props) {
  if (!stage) return null;
  const tone = STAGE_TONE[stage] ?? "border-border text-fg";
  return (
    <span
      className={`inline-flex items-center rounded-full border bg-surface px-2.5 py-0.5 text-xs font-medium ${tone} ${className}`}
    >
      {stageLabel(stage)}
    </span>
  );
}
