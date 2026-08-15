import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusPill } from "@/components/ui/status-pill";
import { testLlmProviders } from "@/lib/api";
import type { LLMProviderTestOut } from "@/lib/types";

function toneFor(result: LLMProviderTestOut): "muted" | "success" | "destructive" {
  if (!result.configured) return "muted";
  return result.ok ? "success" : "destructive";
}

function labelFor(result: LLMProviderTestOut): string {
  if (!result.configured) return "not configured";
  if (result.ok) return `ok · ${result.latency_ms}ms`;
  return "unreachable";
}

export function LlmProviderPanel({ workspaceId }: { workspaceId: string }): React.JSX.Element {
  const [results, setResults] = React.useState<LLMProviderTestOut[] | null>(null);
  const [testing, setTesting] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const handleTest = async (): Promise<void> => {
    setTesting(true);
    setErrorMessage(null);
    try {
      const result = await testLlmProviders(workspaceId);
      setResults(result);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setTesting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">LLM provider connection</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div>
          <Button variant="outline" size="sm" disabled={testing} onClick={() => void handleTest()}>
            {testing ? "Testing…" : "Test connections"}
          </Button>
        </div>

        {errorMessage ? <p className="text-sm text-destructive">{errorMessage}</p> : null}

        {results ? (
          <div className="flex flex-col gap-2">
            {results.map((result) => (
              <div
                key={result.provider}
                className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2"
              >
                <span className="text-sm font-medium capitalize">{result.provider}</span>
                <div className="flex items-center gap-2">
                  <StatusPill status={labelFor(result)} tone={toneFor(result)} />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Run a connection test to see which providers are reachable.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
