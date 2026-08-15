import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { LoadingSkeleton } from "@/components/layout/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Timestamp } from "@/components/ui/timestamp";
import { createApiKey, listApiKeys, revokeApiKey } from "@/lib/api";
import type { ApiKeyCreatedOut } from "@/lib/types";

export function ApiKeysPanel({ workspaceId }: { workspaceId: string }): React.JSX.Element {
  const queryClient = useQueryClient();
  const [name, setName] = React.useState("");
  const [creating, setCreating] = React.useState(false);
  const [justCreatedKey, setJustCreatedKey] = React.useState<ApiKeyCreatedOut | null>(null);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const keysQuery = useQuery({
    queryKey: ["apikeys", workspaceId],
    queryFn: () => listApiKeys(workspaceId),
  });

  const invalidate = (): void => {
    void queryClient.invalidateQueries({ queryKey: ["apikeys", workspaceId] });
  };

  const handleCreate = async (): Promise<void> => {
    if (!name.trim()) return;
    setCreating(true);
    setErrorMessage(null);
    try {
      const created = await createApiKey(workspaceId, name.trim());
      setJustCreatedKey(created);
      setName("");
      invalidate();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (keyId: string): Promise<void> => {
    setErrorMessage(null);
    try {
      await revokeApiKey(workspaceId, keyId);
      invalidate();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">API keys</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {justCreatedKey ? (
          <div className="flex flex-col gap-2 rounded-md border border-warning/40 bg-warning/10 p-3">
            <p className="text-sm font-medium">Copy this key now — it won't be shown again.</p>
            <code className="break-all rounded bg-muted px-2 py-1 text-sm">
              {justCreatedKey.raw_key}
            </code>
            <div>
              <Button variant="outline" size="sm" onClick={() => setJustCreatedKey(null)}>
                Done, I've copied it
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="ingest webhook — pagerduty"
                aria-label="New API key name"
              />
            </div>
            <Button disabled={creating || !name.trim()} onClick={() => void handleCreate()}>
              {creating ? "Creating…" : "Create key"}
            </Button>
          </div>
        )}

        {errorMessage ? <p className="text-sm text-destructive">{errorMessage}</p> : null}

        {keysQuery.isLoading ? (
          <LoadingSkeleton lines={2} />
        ) : keysQuery.isError ? (
          <p className="text-sm text-destructive">Couldn't load API keys.</p>
        ) : keysQuery.data && keysQuery.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">No API keys yet.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {(keysQuery.data ?? []).map((key) => (
              <div
                key={key.id}
                className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{key.name}</p>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <code>{key.prefix}…</code>
                    {key.last_used_at ? (
                      <span>
                        last used <Timestamp value={key.last_used_at} />
                      </span>
                    ) : (
                      <span>never used</span>
                    )}
                  </div>
                </div>
                {key.revoked_at ? (
                  <span className="text-xs text-muted-foreground">revoked</span>
                ) : (
                  <Button variant="ghost" size="sm" onClick={() => void handleRevoke(key.id)}>
                    Revoke
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
