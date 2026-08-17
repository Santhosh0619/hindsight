import { cn } from "@/lib/utils";

// A tiny three-node graph, echoing TechBackground's real visual motif at brand scale --
// used everywhere the "Hindsight" wordmark appears (Landing/Login/Signup header,
// AppShell sidebar) so the same shape reads at both scales instead of the wordmark
// being unrelated to the background it sits in front of.
export function Logomark({ className }: { className?: string }): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" className={cn("h-5 w-5", className)} aria-hidden="true" fill="none">
      <line x1="6" y1="17" x2="12" y2="7" stroke="var(--color-border)" strokeWidth="1.4" />
      <line x1="12" y1="7" x2="18" y2="14" stroke="var(--color-border)" strokeWidth="1.4" />
      <line
        x1="6"
        y1="17"
        x2="18"
        y2="14"
        stroke="var(--color-accent)"
        strokeWidth="1.4"
        opacity="0.7"
      />
      <circle cx="12" cy="7" r="2.4" fill="var(--color-accent)" />
      <circle cx="6" cy="17" r="1.8" fill="var(--color-accent-2)" />
      <circle cx="18" cy="14" r="1.8" fill="var(--color-accent-2)" />
    </svg>
  );
}
