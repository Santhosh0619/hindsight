import * as React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { TechBackground } from "@/components/layout/TechBackground";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth, ApiError } from "@/lib/auth";

interface LocationState {
  from?: { pathname: string };
}

export function Login(): React.JSX.Element {
  const { login, loginAsDemo } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

  const redirectTo = (location.state as LocationState | null)?.from?.pathname ?? "/dashboard";

  const handleSubmit = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleDemo = async (): Promise<void> => {
    setError(null);
    setLoading(true);
    try {
      await loginAsDemo();
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't start a demo session.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center px-4">
      <TechBackground />
      <Link to="/" className="absolute left-6 top-6 text-sm font-semibold tracking-tight">
        Hindsight
      </Link>
      <Card className="w-full max-w-sm border-border/60 bg-card/70 backdrop-blur-md">
        <CardHeader>
          <CardTitle>Log in</CardTitle>
          <CardDescription>Welcome back to Hindsight.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            {error ? <p className="text-sm text-destructive">{error}</p> : null}

            <Button type="submit" disabled={loading}>
              {loading ? "Logging in…" : "Log in"}
            </Button>
          </form>

          <div className="mt-4 flex flex-col gap-2 text-center text-sm">
            <Button variant="link" size="sm" onClick={() => void handleDemo()} disabled={loading}>
              Try the demo instead
            </Button>
            <p className="text-muted-foreground">
              No account?{" "}
              <Link to="/signup" className="text-accent underline-offset-4 hover:underline">
                Sign up
              </Link>
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
