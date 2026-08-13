// Decorative-only background for the public-facing marketing surface (Landing, Login,
// Signup) — a dark base, a faint circuit-grid, and two slow-drifting accent glows.
// Purely CSS/gradient, no external image asset: nothing to license, nothing to fetch,
// nothing that can 404. Never used inside AppShell — the app interior stays calm and
// dense per plan.md's "operations tool, not a marketing site" direction.
export function TechBackground(): React.JSX.Element {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-background">
      <div className="bg-tech-grid absolute inset-0 [mask-image:radial-gradient(ellipse_80%_60%_at_50%_0%,black,transparent)]" />

      <div
        className="animate-drift absolute -left-40 -top-40 h-[36rem] w-[36rem] rounded-full opacity-30 blur-3xl"
        style={{
          background: "radial-gradient(circle, var(--color-accent) 0%, transparent 70%)",
        }}
      />
      <div
        className="animate-drift-slow absolute -right-32 top-1/3 h-[30rem] w-[30rem] rounded-full opacity-25 blur-3xl"
        style={{
          background: "radial-gradient(circle, var(--color-accent-2) 0%, transparent 70%)",
        }}
      />

      <div className="absolute inset-0 bg-[radial-gradient(ellipse_100%_60%_at_50%_100%,var(--color-background)_20%,transparent)]" />
    </div>
  );
}
