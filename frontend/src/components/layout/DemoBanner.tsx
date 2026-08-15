import { useIsDemoWorkspace } from "@/lib/auth";

export function DemoBanner(): React.JSX.Element | null {
  if (!useIsDemoWorkspace()) {
    return null;
  }

  return (
    <div className="border-b border-accent/30 bg-accent/10 px-4 py-1.5 text-center text-xs font-medium text-accent">
      Demo workspace — synthetic data, read-only.
    </div>
  );
}
