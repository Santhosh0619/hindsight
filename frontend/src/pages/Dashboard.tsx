import { useQuery } from "@tanstack/react-query";

import { FragileServicesTable } from "@/components/dashboard/FragileServicesTable";
import { MttrChart } from "@/components/dashboard/MttrChart";
import { RecentBriefsList } from "@/components/dashboard/RecentBriefsList";
import { EmptyState } from "@/components/layout/EmptyState";
import { LoadingSkeleton } from "@/components/layout/LoadingSkeleton";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MetricCard } from "@/components/ui/metric-card";
import { getDashboard } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function Dashboard(): React.JSX.Element {
  const { currentMembership } = useAuth();
  const workspaceId = currentMembership?.workspace_id ?? null;

  const dashboardQuery = useQuery({
    queryKey: ["dashboard", workspaceId],
    queryFn: () => getDashboard(workspaceId as string),
    enabled: Boolean(workspaceId),
  });

  if (!workspaceId || dashboardQuery.isLoading) {
    return <LoadingSkeleton lines={8} />;
  }
  if (dashboardQuery.isError || !dashboardQuery.data) {
    return (
      <EmptyState
        title="Couldn't load the dashboard"
        description="Something went wrong fetching workspace metrics. Try again."
      />
    );
  }

  const data = dashboardQuery.data;
  const ingestTotal =
    data.ingest_health.indexed +
    data.ingest_health.processing +
    data.ingest_health.pending +
    data.ingest_health.failed;

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Where this workspace's incidents, corpus, and briefs stand right now."
      />

      <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <MetricCard label="Open incidents" value={data.open_incidents} />
        <MetricCard label="Briefs generated" value={data.briefs_generated} />
        <MetricCard label="Corpus size" value={data.corpus_size} description="postmortems" />
        <MetricCard
          label="Ingest health"
          value={
            ingestTotal === 0
              ? "—"
              : `${Math.round((data.ingest_health.indexed / ingestTotal) * 100)}%`
          }
          description={ingestTotal === 0 ? "no postmortems yet" : "indexed"}
        />
        <MetricCard
          label="Failed ingests"
          value={data.ingest_health.failed}
          description={
            data.ingest_health.processing > 0
              ? `${data.ingest_health.processing} in flight`
              : undefined
          }
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">MTTR trend</CardTitle>
          </CardHeader>
          <CardContent>
            <MttrChart points={data.mttr_trend} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recent briefs</CardTitle>
          </CardHeader>
          <CardContent>
            <RecentBriefsList briefs={data.recent_briefs} />
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Most fragile services</CardTitle>
          </CardHeader>
          <CardContent>
            <FragileServicesTable services={data.fragile_services} />
          </CardContent>
        </Card>
      </div>
    </>
  );
}
