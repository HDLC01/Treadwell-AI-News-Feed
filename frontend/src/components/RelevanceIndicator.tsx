import { tierLabel, score as fmtScore } from "../lib/format";
import type { RelevanceTier } from "../lib/types";

interface Props {
  tier: RelevanceTier | string | null | undefined;
  score?: number | null;
  showScore?: boolean;
  className?: string;
}

const DOT: Record<string, string> = {
  hot: "bg-hot",
  warm: "bg-warm",
  cold: "bg-cold",
};

const TEXT: Record<string, string> = {
  hot: "text-hot",
  warm: "text-warm-text",
  cold: "text-cold",
};

export default function RelevanceIndicator({
  tier,
  score,
  showScore = false,
  className = "",
}: Props) {
  const key = (tier as string) || "cold";
  const dot = DOT[key] ?? "bg-cold";
  const text = TEXT[key] ?? "text-cold";
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-xs font-semibold ${text} ${className}`}
      title={`Relevance: ${tierLabel(key)}${
        score !== null && score !== undefined ? ` (${fmtScore(score)}/100)` : ""
      }`}
    >
      <span
        className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${dot}`}
        aria-hidden="true"
      />
      <span className="uppercase tracking-wide">{tierLabel(key)}</span>
      {showScore && score !== null && score !== undefined && (
        <span className="num text-fg/70">{fmtScore(score)}</span>
      )}
    </span>
  );
}
