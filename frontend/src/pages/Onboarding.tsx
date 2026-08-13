import { useNavigate } from "react-router-dom";

import { TechBackground } from "@/components/layout/TechBackground";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function Onboarding(): React.JSX.Element {
  const navigate = useNavigate();

  return (
    <div className="relative flex min-h-screen items-center justify-center px-4">
      <TechBackground />
      <div className="flex w-full max-w-2xl flex-col gap-6">
        <div className="text-center">
          <h1 className="text-2xl font-semibold tracking-tight">Set up your workspace</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Your workspace is ready. How do you want to start?
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Card className="border-border/60 bg-card/70 backdrop-blur-md">
            <CardHeader>
              <CardTitle>Seed with demo data</CardTitle>
              <CardDescription>
                A synthetic catalog and postmortem archive to explore the product.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button disabled className="w-full" variant="outline">
                Coming in Phase 11
              </Button>
            </CardContent>
          </Card>

          <Card className="border-border/60 bg-card/70 backdrop-blur-md">
            <CardHeader>
              <CardTitle>Start empty</CardTitle>
              <CardDescription>
                Bring your own service catalog and postmortems later.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button className="w-full" onClick={() => navigate("/dashboard", { replace: true })}>
                Start empty
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
