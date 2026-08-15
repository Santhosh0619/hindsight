import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { RunStatsCards } from "@/components/agent-runs/RunStatsCards";
import { RunWaterfall } from "@/components/agent-runs/RunWaterfall";
import { RunsTable } from "@/components/agent-runs/RunsTable";
import { EmptyState } from "@/components/layout/EmptyState";
import { LoadingSkeleton } from "@/components/layout/LoadingSkeleton";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getAgentRun, getAgentRunStats, listAgentRuns } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function AgentRuns(): React.JSX.Element {
  const { currentMembership } = useAuth();
  const workspaceId = currentMembership?.workspace_id ?? null;
  const [selectedRunId, setSelectedRunId] = React.useState<string | null>(null);

  const runsQuery = useQuery({
    queryKey: ["agent-runs", workspaceId],
    queryFn: () => listAgentRuns(workspaceId as string),
    enabled: Boolean(workspaceId),
  });

  const statsQuery = useQuery({
    queryKey: ["agent-run-stats", workspaceId],
    queryFn: () => getAgentRunStats(workspaceId as string),
    enabled: Boolean(workspaceId),
  });

  const runDetailQuery = useQuery({
    queryKey: ["agent-run", workspaceId, selectedRunId],
    queryFn: () => getAgentRun(workspaceId as string, selectedRunId as string),
    enabled: Boolean(workspaceId) && Boolean(selectedRunId),
  });

  const runs = runsQuery.data?.items ?? [];

  if (!workspaceId || runsQuery.isLoading) {
    return <LoadingSkeleton lines={8} />;
  }
  if (runsQuery.isError) {
    return (
      <EmptyState
        title="Couldn't load agent runs"
        description="Something went wrong fetching agent run history. Try again."
      />
    );
  }

  return (
    <>
      <PageHeader
        title="Agent Runs"
        description="Every brief-generation pipeline run, with per-step token usage and timing."
      />

      <RunStatsCards stats={statsQuery.data ?? null} />

      {runs.length === 0 ? (
        <EmptyState
          title="No agent runs yet"
          description="Generate a brief from an incident to see its pipeline run here."
        />
      ) : (
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Runs</CardTitle>
            </CardHeader>
            <CardContent>
              <RunsTable runs={runs} selectedRunId={selectedRunId} onSelectRun={setSelectedRunId} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Step waterfall</CardTitle>
            </CardHeader>
            <CardContent>
              {selectedRunId && runDetailQuery.isLoading ? (
                <LoadingSkeleton lines={4} />
              ) : selectedRunId && (runDetailQuery.isError || !runDetailQuery.data) ? (
                <p className="text-sm text-muted-foreground">Couldn't load this run's steps.</p>
              ) : (
                <RunWaterfall run={runDetailQuery.data ?? null} />
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </>
  );
}
