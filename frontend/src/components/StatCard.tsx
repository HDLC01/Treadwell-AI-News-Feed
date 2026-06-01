import type { LucideIcon } from "lucide-react";

interface Props {
  label: string;
  value: number | string;
  icon: LucideIcon;
  tone?: "default" | "hot" | "primary" | "accent";
  loading?: boolean;
}

const TONE: Record<NonNullable<Props["tone"]>, string> = {
  default: "text-fg",
  hot: "text-hot",
  primary: "text-primary",
  accent: "text-accent",
};

const ICON_TONE: Record<NonNullable<Props["tone"]>, string> = {
  default: "bg-muted text-cold",
  hot: "bg-hot/10 text-hot",
  primary: "bg-primary/10 text-primary",
  accent: "bg-accent/10 text-accent",
};

export default function StatCard({
  label,
  value,
  icon: Icon,
  tone = "default",
  loading = false,
}: Props) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-surface p-3 sm:p-4">
      <span
        className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${ICON_TONE[tone]}`}
      >
        <Icon className="h-5 w-5" aria-hidden="true" />
      </span>
      <div className="min-w-0">
        {loading ? (
          <div className="h-6 w-12 animate-pulse rounded bg-muted" />
        ) : (
          <div className={`num text-xl font-semibold leading-none ${TONE[tone]}`}>
            {typeof value === "number" ? value.toLocaleString("en-US") : value}
          </div>
        )}
        <div className="mt-1 truncate text-xs text-cold">{label}</div>
      </div>
    </div>
  );
}
