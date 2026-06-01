import type { LucideIcon } from "lucide-react";
import { SearchX } from "lucide-react";

interface Props {
  title: string;
  message?: string;
  icon?: LucideIcon;
  action?: React.ReactNode;
}

export default function EmptyState({
  title,
  message,
  icon: Icon = SearchX,
  action,
}: Props) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-surface px-6 py-16 text-center">
      <span className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-full bg-muted text-cold">
        <Icon className="h-7 w-7" aria-hidden="true" />
      </span>
      <h3 className="text-base font-semibold text-fg">{title}</h3>
      {message && (
        <p className="mt-1 max-w-md text-sm text-cold">{message}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
