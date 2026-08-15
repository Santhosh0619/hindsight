import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { AblationTable } from "@/components/evaluation/AblationTable";
import { CaseResultsTable } from "@/components/evaluation/CaseResultsTable";
import { EvalTrendChart } from "@/components/evaluation/EvalTrendChart";
import { MetricCards } from "@/components/evaluation/MetricCards";
import { EmptyState } from "@/components/layout/EmptyState";
import { LoadingSkeleton } from "@/components/layout/LoadingSkeleton";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getEvalRun, listEvalRuns } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { EvalRunOut } from "@/lib/types";

function defaultRunId(runs: EvalRunOut[]): string | null {
  const fullRuns = runs.filter((run) => run.mode === "full");
  const pool = fullRuns.length > 0 ? fullRuns : runs;
  const newest = [...pool].sort((a, b) => b.started_at.localeCompare(a.started_at))[0];
  return newest?.id ?? null;
}

export function Evaluation(): React.JSX.Element {
  const { currentMembership } = useAuth();
  const workspaceId = currentMembership?.workspace_id ?? null;
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const runsQuery = useQuery({
    queryKey: ["eval-runs", workspaceId],
    queryFn: () => listEvalRuns(workspaceId as string),
    enabled: Boolean(workspaceId),
  });

  const activeRunId = selectedRunId ?? (runsQuery.data ? defaultRunId(runsQuery.data) : null);

  const runDetailQuery = useQuery({
    queryKey: ["eval-run", workspaceId, activeRunId],
    queryFn: () => getEvalRun(workspaceId as string, activeRunId as string),
    enabled: Boolean(workspaceId) && Boolean(activeRunId),
  });

  const runs = useMemo(() => runsQuery.data ?? [], [runsQuery.data]);

  if (!workspaceId || runsQuery.isLoading) {
    return <LoadingSkeleton lines={8} />;
  }
  if (runsQuery.isError) {
    return (
      <EmptyState
        title="Couldn't load evaluation runs"
        description="Something went wrong fetching evaluation history. Try again."
      />
    );
  }
  if (runs.length === 0) {
    return (
      <EmptyState
        title="No evaluation runs yet"
        description="Run `make eval` from the operator CLI to score retrieval against the golden case set."
      />
    );
  }

  return (
    <>
      <PageHeader
        title="Evaluation"
        description="Recall, MRR, citation validity, and groundedness measured against the golden eval case set."
      />

      <MetricCards run={runDetailQuery.data ?? null} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Trend across runs</CardTitle>
          </CardHeader>
          <CardContent>
            <EvalTrendChart runs={runs} onSelectRun={setSelectedRunId} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Ablation comparison</CardTitle>
          </CardHeader>
          <CardContent>
            <AblationTable runs={runs} onSelectRun={setSelectedRunId} />
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Case results</CardTitle>
          </CardHeader>
          <CardContent>
            {runDetailQuery.isLoading ? (
              <LoadingSkeleton lines={4} />
            ) : runDetailQuery.isError || !runDetailQuery.data ? (
              <p className="text-sm text-muted-foreground">Couldn't load case results.</p>
            ) : (
              <CaseResultsTable results={runDetailQuery.data.results} />
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
