import { Skeleton } from "@/components/ui/skeleton";

export function LoadingSkeleton({ lines = 3 }: { lines?: number }): React.JSX.Element {
  return (
    <div className="flex flex-col gap-3">
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className="h-4 w-full" />
      ))}
    </div>
  );
}
