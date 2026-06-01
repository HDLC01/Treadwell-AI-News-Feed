interface SkeletonProps {
  className?: string;
}

/** A single shimmering placeholder block. Respects prefers-reduced-motion via index.css. */
export function Skeleton({ className = "" }: SkeletonProps) {
  return <div className={`animate-pulse rounded bg-muted ${className}`} aria-hidden="true" />;
}

/** A card-shaped skeleton matching the ProjectCard footprint, for the feed grid. */
export function ProjectCardSkeleton() {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-2">
        <Skeleton className="h-5 w-2/3" />
        <Skeleton className="h-5 w-12" />
      </div>
      <Skeleton className="h-4 w-1/2" />
      <div className="flex gap-2">
        <Skeleton className="h-6 w-20" />
        <Skeleton className="h-6 w-24" />
      </div>
      <Skeleton className="h-12 w-full" />
      <div className="flex gap-3 pt-1">
        <Skeleton className="h-4 w-16" />
        <Skeleton className="h-4 w-16" />
        <Skeleton className="h-4 w-16" />
      </div>
    </div>
  );
}

interface GridProps {
  count?: number;
}

/** A responsive grid of card skeletons matching the feed layout. */
export function ProjectGridSkeleton({ count = 6 }: GridProps) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <ProjectCardSkeleton key={i} />
      ))}
    </div>
  );
}
