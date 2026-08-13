import * as React from "react";
import { Link, useNavigate } from "react-router-dom";

import { TechBackground } from "@/components/layout/TechBackground";
import { Button } from "@/components/ui/button";
import { useAuth, ApiError } from "@/lib/auth";

export function Landing(): React.JSX.Element {
  const { loginAsDemo } = useAuth();
  const navigate = useNavigate();
  const [demoError, setDemoError] = React.useState<string | null>(null);
  const [demoLoading, setDemoLoading] = React.useState(false);

  const handleTryDemo = async (): Promise<void> => {
    setDemoError(null);
    setDemoLoading(true);
    try {
      await loginAsDemo();
      navigate("/dashboard");
    } catch (err) {
      setDemoError(err instanceof ApiError ? err.message : "Couldn't start a demo session.");
    } finally {
      setDemoLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen flex-col text-foreground">
      <TechBackground />

      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-6">
        <span className="text-lg font-semibold tracking-tight">Hindsight</span>
        <nav className="flex items-center gap-2">
          <Button asChild variant="ghost" size="sm">
            <Link to="/login">Log in</Link>
          </Button>
          <Button asChild size="sm">
            <Link to="/signup">Sign up</Link>
          </Button>
        </nav>
      </header>

      <main className="mx-auto flex max-w-3xl flex-1 flex-col items-center justify-center gap-8 px-6 py-24 text-center">
        <div className="inline-flex items-center gap-2 self-center rounded-full border border-border/60 bg-card/50 px-3 py-1 text-xs text-muted-foreground backdrop-blur-sm">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          Hybrid vector + keyword + graph retrieval
        </div>

        <div className="flex flex-col gap-5">
          <h1 className="text-5xl font-semibold tracking-tight text-balance sm:text-6xl">
            Your team already <span className="text-gradient-accent">solved this incident.</span>
          </h1>
          <p className="mx-auto max-w-xl text-lg text-muted-foreground">
            An alert fires at 2am. Somewhere in your postmortem archive is the exact failure, the
            root cause, and the fix that worked — from fourteen months ago. Hindsight finds it
            before the outage gets worse.
          </p>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row">
          <Button asChild size="lg" className="shadow-[0_0_24px_-4px_var(--color-accent)]">
            <Link to="/signup">Sign up</Link>
          </Button>
          <Button
            size="lg"
            variant="outline"
            className="border-border/60 bg-card/40 backdrop-blur-sm"
            onClick={() => void handleTryDemo()}
            disabled={demoLoading}
          >
            {demoLoading ? "Starting demo…" : "Try the live demo"}
          </Button>
        </div>

        {demoError ? <p className="text-sm text-destructive">{demoError}</p> : null}
        <p className="text-xs text-muted-foreground">No signup required for the demo.</p>
      </main>
    </div>
  );
}
