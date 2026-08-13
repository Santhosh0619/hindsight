import { cn } from "@/lib/utils";

export function StatusPill({
  status,
  tone = "muted",
  className,
}: {
  status: string;
  tone?: "muted" | "success" | "warning" | "destructive";
  className?: string;
}): React.JSX.Element {
  const toneClass = {
    muted: "bg-muted text-muted-foreground",
    success: "bg-success/20 text-success",
    warning: "bg-warning/20 text-warning",
    destructive: "bg-destructive/20 text-destructive",
  }[tone];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        toneClass,
        className
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {status}
    </span>
  );
}
